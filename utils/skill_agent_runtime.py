from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from typing import Any

from utils.skill_agent_constants import ALLOWED_COMMANDS
from utils.skill_agent_exec import (
    _ensure_python_module,
    _missing_executable_hint,
    _resolve_executable,
    _skill_contains_python_module,
)
from utils.skill_agent_paths import (
    _normalize_relative_file_path,
    _rewrite_existing_session_files_to_abs,
    _rewrite_out_arg_to_session_dir,
    _rewrite_uploads_paths_to_session_dir,
)
from utils.tools import _list_dir, _parse_frontmatter, _read_text, _safe_join


class _AgentRuntime:
    def __init__(
        self,
        *,
        skills_root: str | None,
        session_dir: str,
        max_steps: int,
        memory_turns: int,
        custom_variables: dict[str, str] | None = None,
    ) -> None:
        self.skills_root = skills_root
        self.session_dir = session_dir
        self.max_steps = max_steps
        self.memory_turns = memory_turns
        self.custom_variables = custom_variables or {}
        self._skill_metadata_cache: dict[str, dict[str, Any]] = {}
        self._skill_files_listed: set[str] = set()

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
        if not self.skills_root:
            return {"root": None, "skills": []}
        skills: list[dict[str, Any]] = []
        for folder in sorted(os.listdir(self.skills_root)):
            path = os.path.join(self.skills_root, folder)
            if not os.path.isdir(path):
                continue
            skill_md = os.path.join(path, "SKILL.md")
            meta: dict[str, str] = {}
            if os.path.isfile(skill_md):
                meta = _parse_frontmatter(self._replace_template_vars(_read_text(skill_md, 4000)))
            skills.append(
                {
                    "name": meta.get("name") or folder,
                    "folder": folder,
                    "description": self._replace_template_vars(meta.get("description") or ""),
                }
            )
        return {"root": self.skills_root, "skills": skills}

    def get_skill_metadata(self, skill_name: str) -> dict[str, Any]:
        if not self.skills_root:
            return {"error": "skills_root not found"}
        path = _safe_join(self.skills_root, skill_name)
        skill_md = os.path.join(path, "SKILL.md")
        if not os.path.isfile(skill_md):
            return {"error": "SKILL.md not found", "skill": skill_name}
        content = self._replace_template_vars(_read_text(skill_md, 12000))
        meta = _parse_frontmatter(content)
        self._skill_metadata_cache[skill_name] = {"skill": skill_name, "metadata": meta}
        return {"skill": skill_name, "metadata": meta, "skill_md": content}

    def list_skill_files(self, skill_name: str, max_depth: int = 2) -> dict[str, Any]:
        if not self.skills_root:
            return {"error": "skills_root not found"}
        skill_path = _safe_join(self.skills_root, skill_name)
        self._skill_files_listed.add(skill_name)
        return {"skill": skill_name, "entries": _list_dir(skill_path, max_depth=max_depth)}

    def has_listed_skill_files(self, skill_name: str) -> bool:
        return str(skill_name or "").strip() in self._skill_files_listed

    def read_skill_file(self, skill_name: str, relative_path: str, max_chars: int = 12000) -> dict[str, Any]:
        if not self.skills_root:
            return {"error": "skills_root not found"}
        skill_path = _safe_join(self.skills_root, skill_name)
        file_path = _safe_join(skill_path, relative_path)
        if not os.path.isfile(file_path):
            return {"error": "file not found", "path": relative_path}
        return {"path": file_path, "content": self._replace_template_vars(_read_text(file_path, max_chars))}

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
            "session_dir": self.session_dir,
            "custom_variables": self.custom_variables,
        }

    def run_skill_command(
        self,
        *,
        skill_name: str,
        command: list[str],
        cwd_relative: str | None = None,
        auto_install: bool = False,
    ) -> dict[str, Any]:
        if not self.skills_root:
            return {"error": "skills_root not found"}
        if not command:
            return {"error": "command must be a non-empty list"}
        skill_path = _safe_join(self.skills_root, skill_name)
        exe = command[0]
        if exe == "python":
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
        elif exe not in ALLOWED_COMMANDS:
            return {"error": f"command not allowed: {exe}"}
        resolved0 = _resolve_executable(str(command[0] or ""))
        if not resolved0:
            missing = str(command[0] or exe)
            return {"error": "executable_not_found", "exe": missing, "hint": _missing_executable_hint(missing)}
        command = [resolved0] + command[1:]
        command = _rewrite_uploads_paths_to_session_dir(command, session_dir=self.session_dir)
        command = _rewrite_existing_session_files_to_abs(command, session_dir=self.session_dir)
        command = _rewrite_out_arg_to_session_dir(command, session_dir=self.session_dir)
        cwd = skill_path if not cwd_relative else _safe_join(skill_path, cwd_relative)
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
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            # 当 stdout 为空时，补充诊断信息帮助 LLM 定位问题
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
                    "_diagnostic": " | ".join(diag_parts),
                }
            return {"returncode": result.returncode, "stdout": stdout, "stderr": stderr}
        except FileNotFoundError as e:
            return {"error": "executable_not_found", "exe": str(command[0] or exe), "exception": str(e)}
        except Exception as e:
            return {"error": "subprocess_failed", "exe": str(command[0] or exe), "exception": str(e)}

    def run_temp_command(
        self, *, command: list[str], cwd_relative: str | None = None, auto_install: bool = False
    ) -> dict[str, Any]:
        if not command:
            return {"error": "command must be a non-empty list"}
        exe = command[0]
        if exe == "python":
            if "-m" in command:
                module_index = command.index("-m") + 1
                if module_index < len(command):
                    module_name = command[module_index]
                    module_check = _ensure_python_module(str(module_name), auto_install=auto_install, cwd=self.session_dir)
                    if not module_check.get("ok"):
                        return module_check
            command = [sys.executable] + command[1:]
        elif exe not in ALLOWED_COMMANDS:
            return {"error": f"command not allowed: {exe}"}
        resolved0 = _resolve_executable(str(command[0] or ""))
        if not resolved0:
            missing = str(command[0] or exe)
            return {"error": "executable_not_found", "exe": missing, "hint": _missing_executable_hint(missing)}
        command = [resolved0] + command[1:]
        command = _rewrite_uploads_paths_to_session_dir(command, session_dir=self.session_dir)
        command = _rewrite_existing_session_files_to_abs(command, session_dir=self.session_dir)
        os.makedirs(self.session_dir, exist_ok=True)
        cwd = self.session_dir if not cwd_relative else _safe_join(self.session_dir, cwd_relative)
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
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            # 当 stdout 为空时，补充诊断信息帮助 LLM 定位问题
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
                    "_diagnostic": " | ".join(diag_parts),
                }
            return {"returncode": result.returncode, "stdout": stdout, "stderr": stderr}
        except FileNotFoundError as e:
            return {"error": "executable_not_found", "exe": str(command[0] or exe), "exception": str(e)}
        except Exception as e:
            return {"error": "subprocess_failed", "exe": str(command[0] or exe), "exception": str(e)}

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
        # 定位源文件（在 session_dir 下）
        src = _safe_join(self.session_dir, source_path)
        if not os.path.exists(src):
            return {"error": "source_path 不存在", "source_path": source_path, "session_dir": self.session_dir}
        dst = _safe_join(self.skills_root, safe_name)
        # 如果目标已存在，先删除旧版本
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        elif os.path.exists(dst):
            os.remove(dst)
        try:
            if src.lower().endswith(".zip"):
                # zip 文件：解压到目标目录
                os.makedirs(dst, exist_ok=True)
                with zipfile.ZipFile(src, "r") as zf:
                    zf.extractall(dst)
            else:
                # 目录：直接复制
                shutil.copytree(src, dst)
        except Exception as e:
            return {"error": f"安装失败: {str(e)}", "source": src, "destination": dst}
        # 清除该技能的 metadata 缓存，使其立即可被 load_skills_index 发现
        self._skill_metadata_cache.pop(safe_name, None)
        # 验证安装结果
        skill_md = os.path.join(dst, "SKILL.md")
        has_skill_md = os.path.isfile(skill_md)
        return {
            "skill": safe_name,
            "installed_to": dst,
            "has_skill_md": has_skill_md,
            "source_type": "zip" if src.lower().endswith(".zip") else "directory",
        }

    def list_installed_skills(self) -> dict[str, Any]:
        """列出 skills_root 下所有已安装的技能。"""
        if not self.skills_root:
            return {"error": "skills_root 未配置", "skills": []}
        skills: list[dict[str, Any]] = []
        for folder in sorted(os.listdir(self.skills_root)):
            path = os.path.join(self.skills_root, folder)
            if not os.path.isdir(path):
                continue
            skill_md = os.path.join(path, "SKILL.md")
            has_md = os.path.isfile(skill_md)
            meta: dict[str, str] = {}
            if has_md:
                from utils.tools import _parse_frontmatter, _read_text
                meta = _parse_frontmatter(_read_text(skill_md, 4000))
            skills.append({
                "name": meta.get("name") or folder,
                "folder": folder,
                "description": self._replace_template_vars(meta.get("description") or ""),
                "has_skill_md": has_md,
            })
        return {
            "root": self.skills_root,
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
        """覆盖式更新技能：先删除旧版本，再从 source_path 重新安装。"""
        if not self.skills_root:
            return {"error": "skills_root 未配置，无法更新技能。"}
        safe_name = skill_name.replace("/", "").replace("\\", "").replace("..", "").strip()
        if not safe_name:
            return {"error": "skill_name 不能为空或包含非法字符", "skill_name": skill_name}
        target = _safe_join(self.skills_root, safe_name)
        # 检查旧版本是否存在
        if not os.path.isdir(target):
            return {"error": f"技能 '{safe_name}' 不存在，无法更新。请先使用 install_skill 安装。", "skill_name": safe_name}
        # 先删除
        try:
            shutil.rmtree(target, ignore_errors=False)
        except Exception as e:
            return {"error": f"删除旧版本失败: {str(e)}", "skill_name": safe_name}
        # 再安装（复用 install_skill 的逻辑）
        result = self.install_skill(source_path=source_path, skill_name=safe_name)
        if result.get("error"):
            return {**result, "note": "更新过程中删除了旧版本但新版本安装失败，当前处于未安装状态"}
        return {**result, "updated": True}
