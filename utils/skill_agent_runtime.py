from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
import uuid
from typing import Any

from utils.skill_agent_exec import (
    _ensure_python_module,
    _missing_executable_hint,
    _resolve_executable,
    _skill_contains_python_module,
)
from utils.skill_agent_constants import (
    ALLOWED_COMMANDS,
    MAX_ARCHIVE_MEMBERS,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    UNSAFE_COMMANDS,
)
from utils.skill_agent_paths import (
    _normalize_relative_file_path,
    _rewrite_existing_session_files_to_abs,
    _rewrite_out_arg_to_session_dir,
    _rewrite_uploads_paths_to_session_dir,
)
from utils.tools import _list_dir, _parse_frontmatter, _read_text, _safe_join

# 需要从 JSON 响应中自动移除的大字段（通常是嵌套的节点/详情列表，数据量巨大）
_COMPRESS_REMOVE_KEYS = frozenset({"nodeList"})
_SKILL_VERSION_PATTERN = re.compile(
    r"(?im)^\s*(?:当前)?版本\s*[:：]\s*`?v?(\d+\.\d+\.\d+)`?"
)


def _extract_declared_skill_version(content: str) -> str | None:
    """Extract a semver explicitly declared in the SKILL.md body."""
    match = _SKILL_VERSION_PATTERN.search(str(content or ""))
    return match.group(1) if match else None


def _compress_json_value(
    val: Any,
    depth: int = 0,
    max_array_items: int = 20,
    max_str_len: int = 500,
) -> Any:
    """递归压缩 JSON 值：移除大字段、截断长字符串、限制数组长度。"""
    if depth > 10:
        return val
    if isinstance(val, dict):
        return {
            k: _compress_json_value(v, depth + 1, max_array_items, max_str_len)
            for k, v in val.items()
            if k not in _COMPRESS_REMOVE_KEYS
        }
    if isinstance(val, list):
        truncated = val[:max_array_items]
        compressed = [_compress_json_value(item, depth + 1, max_array_items, max_str_len) for item in truncated]
        if len(val) > max_array_items:
            compressed.append(f"... [共 {len(val)} 项，已省略 {len(val) - max_array_items} 项]")
        return compressed
    if isinstance(val, str) and len(val) > max_str_len:
        return val[:max_str_len] + f"... [已截断，原始长度 {len(val)}]"
    return val


def _try_compress_stdout(stdout: str, max_chars: int) -> str:
    """当 stdout 超过 max_chars 时，尝试解析为 JSON 并压缩；失败则简单截断。"""
    if len(stdout) <= max_chars:
        return stdout
    try:
        data = json.loads(stdout)
        # 第一轮压缩：保留 20 项数组、500 字符字符串
        compressed = _compress_json_value(data, max_array_items=20, max_str_len=500)
        result = json.dumps(compressed, ensure_ascii=False)
        if len(result) <= max_chars:
            return result
        # 第二轮压缩：更激进——5 项数组、200 字符字符串
        compressed2 = _compress_json_value(data, max_array_items=5, max_str_len=200)
        result2 = json.dumps(compressed2, ensure_ascii=False)
        if len(result2) <= max_chars:
            return result2
        # 仍然超限，返回压缩后结果并标注
        return result2[:max_chars] + f"\n... [JSON 压缩后仍超限，已截断，原始输出共 {len(stdout)} 字符]"
    except (json.JSONDecodeError, ValueError):
        # 非 JSON，简单截断
        return stdout[:max_chars] + f"\n... [截断，原始输出共 {len(stdout)} 字符]"


class _AgentRuntime:
    def __init__(
        self,
        *,
        skills_root: str | None,
        session_dir: str,
        max_steps: int,
        memory_turns: int,
        custom_variables: dict[str, str] | None = None,
        max_stdout_chars: int = 30000,
        allowed_commands: set[str],  # 由调用方传入（yaml 默认值或用户自定义）
        allow_unsafe_commands: bool = False,
        skill_space: str = "default",
        shared_skills_root: str | None = None,
        enabled_skills: set[str] | None = None,
        expected_skill_version: str | None = None,
    ) -> None:
        self.skills_root = skills_root
        self.shared_skills_root = shared_skills_root
        self.session_dir = session_dir
        self.max_steps = max_steps
        self.memory_turns = memory_turns
        self.custom_variables = custom_variables or {}
        self.max_stdout_chars = max_stdout_chars
        self.skill_space = skill_space
        self.enabled_skills = (
            {str(name).strip() for name in enabled_skills if str(name).strip()}
            if enabled_skills
            else None
        )
        self.expected_skill_version = str(expected_skill_version or "").strip().lstrip("vV") or None
        # The caller may narrow the normal allow-list, but cannot enable shells,
        # installers or network clients without an explicit opt-in.
        requested = {str(x).lower() for x in allowed_commands}
        self.allow_unsafe_commands = allow_unsafe_commands
        self.allowed_commands = requested & (ALLOWED_COMMANDS | (UNSAFE_COMMANDS if allow_unsafe_commands else set()))
        self._skill_metadata_cache: dict[str, dict[str, Any]] = {}
        self._skill_files_listed: set[str] = set()

    def _skill_is_enabled(self, skill_name: str) -> bool:
        return self.enabled_skills is None or str(skill_name or "").strip() in self.enabled_skills

    def _skill_roots(self) -> list[tuple[str, str]]:
        roots: list[tuple[str, str]] = []
        if self.skills_root:
            roots.append((self.skills_root, "private"))
        if self.shared_skills_root:
            shared_abs = os.path.abspath(self.shared_skills_root)
            if not any(os.path.abspath(root) == shared_abs for root, _ in roots):
                roots.append((self.shared_skills_root, "shared"))
        return roots

    def _resolve_skill(self, skill_name: str) -> tuple[str | None, str | None, dict[str, Any] | None]:
        name = str(skill_name or "").strip()
        if not name:
            return None, None, {"error": "skill_name 不能为空", "skill_name": skill_name}
        if not self._skill_is_enabled(name):
            return None, None, {
                "error": "skill_not_enabled",
                "skill": name,
                "detail": "当前工作流未启用该技能。",
            }
        for root, scope in self._skill_roots():
            try:
                path = _safe_join(root, name)
            except Exception as exc:
                return None, None, {"error": "invalid skill_name", "skill": name, "exception": str(exc)}
            if os.path.isdir(path) and os.path.isfile(os.path.join(path, "SKILL.md")):
                return path, scope, None
        return None, None, {"error": "skill_not_found", "skill": name}

    def validate_skill_selection(self) -> dict[str, Any]:
        """Fail closed when a workflow selects missing skills or a wrong version."""
        if self.enabled_skills:
            missing = []
            for name in sorted(self.enabled_skills):
                _, _, error = self._resolve_skill(name)
                if error:
                    missing.append(name)
            if missing:
                return {
                    "error": "configured_skills_not_found",
                    "skill_space": self.skill_space,
                    "missing_skills": missing,
                }
        if self.expected_skill_version:
            if not self.enabled_skills or len(self.enabled_skills) != 1:
                return {
                    "error": "skill_version_requires_one_enabled_skill",
                    "skill_space": self.skill_space,
                    "detail": "配置 skill_version 时，enabled_skills 必须且只能填写一个技能名称。",
                }
            name = next(iter(self.enabled_skills))
            path, _, error = self._resolve_skill(name)
            if error or not path:
                return error or {"error": "skill_not_found", "skill": name}
            content = _read_text(os.path.join(path, "SKILL.md"), 12000)
            metadata = _parse_frontmatter(content)
            actual = str(metadata.get("version") or _extract_declared_skill_version(content) or "").strip().lstrip("vV")
            if actual != self.expected_skill_version:
                return {
                    "error": "skill_version_mismatch",
                    "skill_space": self.skill_space,
                    "skill": name,
                    "expected_version": self.expected_skill_version,
                    "actual_version": actual or None,
                }
        return {"ok": True}

    def _replace_template_vars(self, text: str) -> str:
        """将文本中 ${xxx} 格式的占位符替换为 custom_variables 中对应字段的值。"""
        if not self.custom_variables or not text:
            return text

        def _replacer(match: re.Match) -> str:
            key = match.group(1)
            return str(self.custom_variables.get(key, match.group(0)))

        return re.sub(r"\$\{(\w+)\}", _replacer, text)

    def _build_subprocess_env(self) -> dict[str, str]:
        """构建子进程环境变量，将 custom_variables 注入为环境变量。"""
        env = dict(os.environ)
        for key, value in self.custom_variables.items():
            # 将变量名转为大写并替换 - 为 _，如 iv-user → IV_USER
            env_key = key.upper().replace("-", "_")
            env[env_key] = str(value)
        return env

    def has_skill_metadata(self, skill_name: str) -> bool:
        cached = self._skill_metadata_cache.get(skill_name)
        return bool(isinstance(cached, dict) and cached.get("skill") == skill_name)

    def load_skills_index(self) -> dict[str, Any]:
        if not self._skill_roots():
            return {"root": None, "skill_space": self.skill_space, "skills": []}
        skills: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root, scope in self._skill_roots():
            for folder in sorted(os.listdir(root)):
                if folder.startswith(".") or folder in seen or not self._skill_is_enabled(folder):
                    continue
                path = os.path.join(root, folder)
                if not os.path.isdir(path):
                    continue
                skill_md = os.path.join(path, "SKILL.md")
                if not os.path.isfile(skill_md):
                    continue
                content = self._replace_template_vars(_read_text(skill_md, 4000))
                meta = _parse_frontmatter(content)
                version = str(meta.get("version") or _extract_declared_skill_version(content) or "").strip().lstrip("vV")
                skills.append(
                    {
                        "name": meta.get("name") or folder,
                        "folder": folder,
                        "description": self._replace_template_vars(meta.get("description") or ""),
                        "version": version or None,
                        "scope": scope,
                    }
                )
                seen.add(folder)
        return {"root": self.skills_root, "skill_space": self.skill_space, "skills": skills}

    def get_skill_metadata(self, skill_name: str) -> dict[str, Any]:
        path, scope, error = self._resolve_skill(skill_name)
        if error or not path:
            return error or {"error": "skill_not_found", "skill": skill_name}
        skill_md = os.path.join(path, "SKILL.md")
        if not os.path.isfile(skill_md):
            return {"error": "SKILL.md not found", "skill": skill_name}
        content = self._replace_template_vars(_read_text(skill_md, 12000))
        meta = _parse_frontmatter(content)
        declared_version = _extract_declared_skill_version(content)
        if declared_version:
            meta["version"] = declared_version
        self._skill_metadata_cache[skill_name] = {"skill": skill_name, "metadata": meta}
        return {"skill": skill_name, "scope": scope, "metadata": meta, "skill_md": content}

    def list_skill_files(self, skill_name: str, max_depth: int = 2) -> dict[str, Any]:
        skill_path, scope, error = self._resolve_skill(skill_name)
        if error or not skill_path:
            return error or {"error": "skill_not_found", "skill": skill_name}
        self._skill_files_listed.add(skill_name)
        return {"skill": skill_name, "scope": scope, "entries": _list_dir(skill_path, max_depth=max_depth)}

    def has_listed_skill_files(self, skill_name: str) -> bool:
        return str(skill_name or "").strip() in self._skill_files_listed

    def read_skill_file(self, skill_name: str, relative_path: str, max_chars: int = 12000) -> dict[str, Any]:
        skill_path, scope, error = self._resolve_skill(skill_name)
        if error or not skill_path:
            return error or {"error": "skill_not_found", "skill": skill_name}
        file_path = _safe_join(skill_path, relative_path)
        if not os.path.isfile(file_path):
            return {"error": "file not found", "path": relative_path}
        return {"path": file_path, "scope": scope, "content": self._replace_template_vars(_read_text(file_path, max_chars))}

    def write_temp_file(self, relative_path: str, content: str) -> dict[str, Any]:
        os.makedirs(self.session_dir, exist_ok=True)
        rp = _normalize_relative_file_path(relative_path)
        if not rp:
            return {"error": "invalid relative_path", "relative_path": relative_path}
        try:
            path = _safe_join(self.session_dir, rp)
        except Exception as e:
            return {"error": "invalid relative_path", "relative_path": relative_path, "exception": str(e)}
        if os.path.isdir(path):
            return {"error": "path is a directory", "relative_path": relative_path, "path": path}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content or "")
        except Exception as e:
            return {"error": "write failed", "relative_path": relative_path, "path": path, "exception": str(e)}
        return {"path": path, "bytes": len((content or "").encode("utf-8"))}

    def read_temp_file(self, relative_path: str, max_chars: int = 12000) -> dict[str, Any]:
        os.makedirs(self.session_dir, exist_ok=True)
        rp = _normalize_relative_file_path(relative_path)
        if not rp:
            return {"error": "invalid relative_path", "relative_path": relative_path}
        try:
            path = _safe_join(self.session_dir, rp)
        except Exception as e:
            return {"error": "invalid relative_path", "relative_path": relative_path, "exception": str(e)}
        if os.path.isdir(path):
            return {"error": "path is a directory", "relative_path": relative_path, "path": path}
        if not os.path.isfile(path):
            return {"error": "file not found", "relative_path": relative_path}
        try:
            return {"path": path, "content": _read_text(path, max_chars)}
        except Exception as e:
            return {"error": "read failed", "relative_path": relative_path, "path": path, "exception": str(e)}

    def list_temp_files(self, max_depth: int = 4) -> dict[str, Any]:
        os.makedirs(self.session_dir, exist_ok=True)
        return {"session_dir": self.session_dir, "entries": _list_dir(self.session_dir, max_depth=max_depth)}

    def get_session_context(self) -> dict[str, Any]:
        return {
            "skills_root": self.skills_root,
            "shared_skills_root": self.shared_skills_root,
            "skill_space": self.skill_space,
            "enabled_skills": sorted(self.enabled_skills) if self.enabled_skills else [],
            "expected_skill_version": self.expected_skill_version,
            "session_dir": self.session_dir,
            "custom_variables": self.custom_variables,
        }

    def _execute_command(
        self,
        *,
        command: list[str],
        cwd: str,
        exe_fallback: str = "",
    ) -> dict[str, Any]:
        """公共命令执行逻辑：解析可执行文件、重写路径、执行子进程、处理输出。

        被 run_skill_command 和 run_temp_command 共用，消除约 80% 的重复代码。
        """
        resolved0 = _resolve_executable(str(command[0] or ""))
        if not resolved0:
            missing = str(command[0] or exe_fallback)
            return {"error": "executable_not_found", "exe": missing, "hint": _missing_executable_hint(missing)}
        command = [resolved0] + command[1:]
        command = _rewrite_uploads_paths_to_session_dir(command, session_dir=self.session_dir)
        command = _rewrite_existing_session_files_to_abs(command, session_dir=self.session_dir)
        env = self._build_subprocess_env()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                env=env,
                # 隔离子进程 stdin，防止子进程通过继承的 stdin 偷读
                # plugin_daemon 与插件之间的 stdio 协议管道导致后续调用全部卡死
                stdin=subprocess.DEVNULL,
                timeout=300,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            stdout = _try_compress_stdout(stdout, self.max_stdout_chars)
            if not stdout:
                diag_parts = [f"returncode={result.returncode}"]
                if stderr:
                    diag_parts.append(f"stderr={stderr}")
                else:
                    diag_parts.append("(stderr also empty)")
                diag_parts.append(f"command={' '.join(command)}")
                return {
                    "returncode": result.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "command": command,
                    "cwd": cwd,
                    "_diagnostic": " | ".join(diag_parts),
                }
            return {"returncode": result.returncode, "stdout": stdout, "stderr": stderr, "command": command, "cwd": cwd}
        except FileNotFoundError as e:
            return {"error": "executable_not_found", "exe": str(command[0] or exe_fallback), "exception": str(e)}
        except subprocess.TimeoutExpired as e:
            return {"error": "command_timeout", "exe": str(command[0] or exe_fallback), "timeout_seconds": 300, "exception": f"命令执行超过 300 秒超时: {str(e)}"}
        except Exception as e:
            return {"error": "subprocess_failed", "exe": str(command[0] or exe_fallback), "exception": str(e)}

    def run_skill_command(
        self,
        *,
        skill_name: str,
        command: list[str],
        cwd_relative: str | None = None,
        auto_install: bool = False,
    ) -> dict[str, Any]:
        if not command:
            return {"error": "command must be a non-empty list"}
        skill_path, _, error = self._resolve_skill(skill_name)
        if error or not skill_path:
            return error or {"error": "skill_not_found", "skill": skill_name}
        exe = command[0]
        if not self.allow_unsafe_commands and auto_install:
            return {"error": "auto_install requires allow_unsafe_commands=true"}
        if not self.allow_unsafe_commands and exe in ("python", "python3", "node") and ("-c" in command or "-e" in command or "-" in command[1:]):
            return {"error": "inline code execution requires allow_unsafe_commands=true"}
        if exe in ("python", "python3"):
            if "-m" in command:
                module_index = command.index("-m") + 1
                if module_index < len(command):
                    module_name = command[module_index]
                    if not _skill_contains_python_module(skill_path, str(module_name)):
                        return {
                            "error": "no_executable_found",
                            "skill": skill_name,
                            "reason": "python -m module not found in skill folder",
                            "module": str(module_name),
                        }
                    module_check = _ensure_python_module(str(module_name), auto_install=auto_install, cwd=self.session_dir)
                    if not module_check.get("ok"):
                        return module_check
            command = [sys.executable] + command[1:]
        elif exe.lower() not in self.allowed_commands:
            return {"error": f"command not allowed: {exe}"}
        # 技能命令额外重写 --out 参数到 session_dir
        command = _rewrite_out_arg_to_session_dir(command, session_dir=self.session_dir)
        cwd = skill_path if not cwd_relative else _safe_join(skill_path, cwd_relative)
        return self._execute_command(command=command, cwd=cwd, exe_fallback=exe)

    def run_temp_command(
        self, *, command: list[str], cwd_relative: str | None = None, auto_install: bool = False
    ) -> dict[str, Any]:
        if not command:
            return {"error": "command must be a non-empty list"}
        exe = command[0]
        if not self.allow_unsafe_commands and auto_install:
            return {"error": "auto_install requires allow_unsafe_commands=true"}
        if not self.allow_unsafe_commands and exe in ("python", "python3", "node") and ("-c" in command or "-e" in command or "-m" in command or "-" in command[1:]):
            return {"error": "inline/module execution in temp requires allow_unsafe_commands=true"}
        if exe in ("python", "python3"):
            if "-m" in command:
                module_index = command.index("-m") + 1
                if module_index < len(command):
                    module_name = command[module_index]
                    module_check = _ensure_python_module(str(module_name), auto_install=auto_install, cwd=self.session_dir)
                    if not module_check.get("ok"):
                        return module_check
            command = [sys.executable] + command[1:]
        elif exe.lower() not in self.allowed_commands:
            return {"error": f"command not allowed: {exe}"}
        os.makedirs(self.session_dir, exist_ok=True)
        cwd = self.session_dir if not cwd_relative else _safe_join(self.session_dir, cwd_relative)
        return self._execute_command(command=command, cwd=cwd, exe_fallback=exe)

    def export_temp_file(
        self,
        *,
        temp_relative_path: str,
        workspace_relative_path: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        os.makedirs(self.session_dir, exist_ok=True)
        rp = _normalize_relative_file_path(temp_relative_path)
        if not rp:
            return {"error": "invalid temp_relative_path", "temp_relative_path": temp_relative_path}
        try:
            src = _safe_join(self.session_dir, rp)
        except Exception as e:
            return {"error": "invalid temp_relative_path", "temp_relative_path": temp_relative_path, "exception": str(e)}
        if os.path.isdir(src):
            return {"error": "source path is a directory", "temp_relative_path": temp_relative_path, "source": src}
        if not os.path.isfile(src):
            return {"error": "source file not found", "temp_relative_path": temp_relative_path}
        return {
            "source": src,
            "relative_path": temp_relative_path,
            "bytes": os.path.getsize(src),
            "note": "export_temp_file does not copy files; tool marks final output only",
            "requested_name": workspace_relative_path,
            "overwrite": overwrite,
        }

    # ==================== 技能管理方法 ====================

    def install_skill(self, *, source_path: str, skill_name: str) -> dict[str, Any]:
        """将 session_dir 下的目录或 zip 安装到 skills_root/<skill_name>/。"""
        if not self.skills_root:
            return {"error": "skills_root 未配置，无法安装技能。请确认插件包中存在 skills/ 目录或已设置 skills_root 参数/环境变量。"}
        # 安全化 skill_name，防止路径穿越
        safe_name = skill_name.replace("/", "").replace("\\", "").replace("..", "").strip()
        if not safe_name:
            return {"error": "skill_name 不能为空或包含非法字符", "skill_name": skill_name}
        if not self._skill_is_enabled(safe_name):
            return {"error": "skill_not_enabled", "skill": safe_name, "detail": "当前工作流未启用该技能。"}
        # 定位源文件（在 session_dir 下）
        src = _safe_join(self.session_dir, source_path)
        if not os.path.exists(src):
            return {"error": "source_path 不存在", "source_path": source_path, "session_dir": self.session_dir}
        dst = _safe_join(self.skills_root, safe_name)
        staging = _safe_join(self.skills_root, f".{safe_name}.staging-{uuid.uuid4().hex}")
        try:
            if src.lower().endswith(".zip"):
                # Validate archive size before writing anything to disk.
                os.makedirs(staging, exist_ok=False)
                with zipfile.ZipFile(src, "r") as zf:
                    infos = zf.infolist()
                    if len(infos) > MAX_ARCHIVE_MEMBERS:
                        raise ValueError(f"压缩包文件数超过限制（{MAX_ARCHIVE_MEMBERS}）")
                    total_size = sum(max(0, info.file_size) for info in infos)
                    if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise ValueError("压缩包解压后大小超过限制")
                    for info in infos:
                        name = info.filename
                        if not name:
                            continue
                        # 拒绝绝对路径和 .. 路径穿越
                        if name.startswith("/") or name.startswith("\\") or ".." in name:
                            raise ValueError("压缩包包含非法路径（可能为 zip slip 攻击）")
                        target_path = os.path.realpath(os.path.join(staging, name))
                        # 确保解压目标仍在 dst 目录内
                        if not target_path.startswith(os.path.realpath(staging) + os.sep):
                            raise ValueError("压缩包包含越权路径（可能为 zip slip 攻击）")
                        if info.is_dir():
                            os.makedirs(target_path, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            with zf.open(info) as src_f, open(target_path, "wb") as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
            else:
                # 目录：直接复制
                shutil.copytree(src, staging)
            skill_md = os.path.join(staging, "SKILL.md")
            if not os.path.isfile(skill_md):
                raise ValueError("安装包根目录缺少 SKILL.md")
            backup = _safe_join(self.skills_root, f".{safe_name}.backup-{uuid.uuid4().hex}")
            if os.path.exists(dst):
                os.replace(dst, backup)
            try:
                os.replace(staging, dst)
            except Exception:
                if os.path.exists(backup):
                    os.replace(backup, dst)
                raise
            if os.path.exists(backup):
                shutil.rmtree(backup)
        except Exception as e:
            shutil.rmtree(staging, ignore_errors=True)
            return {"error": f"安装失败: {str(e)}", "source": src, "destination": dst}
        # 清除该技能的 metadata 缓存，使其立即可被 load_skills_index 发现
        self._skill_metadata_cache.pop(safe_name, None)
        # 验证安装结果
        return {
            "skill": safe_name,
            "installed_to": dst,
            "has_skill_md": True,
            "source_type": "zip" if src.lower().endswith(".zip") else "directory",
        }

    def list_installed_skills(self) -> dict[str, Any]:
        """列出当前空间可见的私有技能和可选公共只读技能。"""
        if not self._skill_roots():
            return {"error": "skills_root 未配置", "skills": []}
        skills: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root, scope in self._skill_roots():
            for folder in sorted(os.listdir(root)):
                if folder.startswith(".") or folder in seen or not self._skill_is_enabled(folder):
                    continue
                path = os.path.join(root, folder)
                if not os.path.isdir(path):
                    continue
                skill_md = os.path.join(path, "SKILL.md")
                has_md = os.path.isfile(skill_md)
                meta: dict[str, str] = {}
                if has_md:
                    meta = _parse_frontmatter(_read_text(skill_md, 4000))
                skills.append({
                    "name": meta.get("name") or folder,
                    "folder": folder,
                    "description": self._replace_template_vars(meta.get("description") or ""),
                    "has_skill_md": has_md,
                    "scope": scope,
                })
                seen.add(folder)
        return {
            "root": self.skills_root,
            "skill_space": self.skill_space,
            "skills_count": len(skills),
            "skills": skills,
        }

    def uninstall_skill(self, *, skill_name: str) -> dict[str, Any]:
        """按名称从 skills_root 删除技能。"""
        if not self.skills_root:
            return {"error": "skills_root 未配置，无法删除技能。"}
        safe_name = skill_name.replace("/", "").replace("\\", "").replace("..", "").strip()
        if not safe_name:
            return {"error": "skill_name 不能为空或包含非法字符", "skill_name": skill_name}
        if not self._skill_is_enabled(safe_name):
            return {"error": "skill_not_enabled", "skill": safe_name, "detail": "当前工作流未启用该技能。"}
        target = _safe_join(self.skills_root, safe_name)
        if not os.path.isdir(target):
            return {"error": "技能不存在", "skill_name": safe_name, "skills_root": self.skills_root}
        try:
            shutil.rmtree(target, ignore_errors=False)
        except Exception as e:
            return {"error": f"删除失败: {str(e)}", "skill_name": safe_name, "path": target}
        # 清除缓存
        self._skill_metadata_cache.pop(safe_name, None)
        return {"skill": safe_name, "uninstalled": True, "path": target}

    def update_skill(self, *, skill_name: str, source_path: str) -> dict[str, Any]:
        """覆盖式更新技能：通过 install_skill 的 staging + replace 保留旧版本直到新版本可用。"""
        if not self.skills_root:
            return {"error": "skills_root 未配置，无法更新技能。"}
        safe_name = skill_name.replace("/", "").replace("\\", "").replace("..", "").strip()
        if not safe_name:
            return {"error": "skill_name 不能为空或包含非法字符", "skill_name": skill_name}
        if not self._skill_is_enabled(safe_name):
            return {"error": "skill_not_enabled", "skill": safe_name, "detail": "当前工作流未启用该技能。"}
        target = _safe_join(self.skills_root, safe_name)
        # 检查旧版本是否存在
        if not os.path.isdir(target):
            return {"error": f"技能 '{safe_name}' 不存在，无法更新。请先使用 install_skill 安装。", "skill_name": safe_name}
        # install_skill performs an atomic replacement and restores the old version
        # if activation fails.
        result = self.install_skill(source_path=source_path, skill_name=safe_name)
        if result.get("error"):
            return {**result, "note": "新版本未安装成功，已保留旧版本"}
        return {**result, "updated": True}
