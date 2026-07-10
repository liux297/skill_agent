from __future__ import annotations

import mimetypes
import re
import shutil
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# 复用 utils/tools.py 中的公共工具函数，消除重复实现
from utils.skill_agent_constants import MAX_ARCHIVE_MEMBERS, MAX_ARCHIVE_UNCOMPRESSED_BYTES, MAX_UPLOAD_BYTES
from utils.tools import _download_file_content, _extract_url_and_name, _infer_ext_from_url, _safe_filename


def get_file_content(url: str, timeout: int = 30) -> bytes:
    try:
        return _download_file_content(url, timeout=timeout, max_bytes=MAX_UPLOAD_BYTES)
    except Exception as e:
        raise RuntimeError(f"文件下载失败: {str(e)}") from e


def get_skills_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    skills_dir = root / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


def list_skills_sorted() -> list[Path]:
    skills_dir = get_skills_dir()
    folders = [p for p in skills_dir.iterdir() if p.is_dir()]
    folders.sort(key=lambda p: p.stat().st_ctime)
    return folders


def _is_within_dir(base: Path, target: Path) -> bool:
    try:
        base_resolved = base.resolve()
        target_resolved = target.resolve()
        return base_resolved == target_resolved or base_resolved in target_resolved.parents
    except Exception:
        return False


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise RuntimeError(f"压缩包文件数超过限制（{MAX_ARCHIVE_MEMBERS}）")
        if sum(max(0, info.file_size) for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise RuntimeError("压缩包解压后大小超过限制")
        for info in infos:
            name = info.filename
            if not name:
                continue
            if name.startswith("/") or name.startswith("\\"):
                raise RuntimeError("压缩包包含非法路径")
            target_path = (dest_dir / name).resolve()
            if not _is_within_dir(dest_dir, target_path):
                raise RuntimeError("压缩包包含越权路径")
            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _find_skill_folders(extracted_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for p in extracted_root.iterdir():
        if p.is_dir():
            candidates.append(p)
    if candidates:
        with_skill_md = [p for p in candidates if (p / "SKILL.md").is_file()]
        if with_skill_md:
            return with_skill_md
        if len(candidates) == 1:
            return candidates
        return candidates
    if (extracted_root / "SKILL.md").is_file():
        return [extracted_root]
    return []


class TMTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        command = str(tool_parameters.get("command", "")).strip()
        files_param = tool_parameters.get("files")

        if command in ("查看技能", "查看 技能", "查看"):
            skills = list_skills_sorted()
            if not skills:
                yield self.create_text_message("❌当前没有已存入的技能包。\n")
                return
            lines = [f"{idx + 1}. {p.name}" for idx, p in enumerate(skills)]
            yield self.create_text_message("\n".join(lines))
            return

        if command in ("新增技能", "存入技能", "保存技能"):
            file_items: list[Any] = []
            if isinstance(files_param, list):
                file_items = [x for x in files_param if x]
            elif files_param:
                file_items = [files_param]
            elif "file" in tool_parameters and tool_parameters["file"]:
                file_items = [tool_parameters["file"]]

            if not file_items:
                yield self.create_text_message("❌未检测到上传的 zip 文件，请提供 files 参数。\n")
                return

            skills_dir = get_skills_dir()
            installed: list[str] = []

            for file_item in file_items:
                url, preferred_name = _extract_url_and_name(file_item)
                if not url:
                    yield self.create_text_message("❌无法获取文件URL，请检查入参（files[i].url）。\n")
                    return

                filename_attr = None
                try:
                    filename_attr = getattr(file_item, "filename", None)
                except Exception:
                    filename_attr = None
                if isinstance(file_item, dict):
                    filename_attr = file_item.get("filename", filename_attr)

                try:
                    content = get_file_content(url)
                except Exception as e:
                    yield self.create_text_message(str(e))
                    return

                if filename_attr:
                    filename = Path(filename_attr).name
                else:
                    ext = _infer_ext_from_url(url)
                    filename = _safe_filename(preferred_name, fallback_ext=ext if ext else ".zip")

                with tempfile.TemporaryDirectory(prefix="skill-upload-") as td:
                    tmp_dir = Path(td)
                    zip_path = tmp_dir / filename
                    try:
                        zip_path.write_bytes(content)
                    except Exception as e:
                        yield self.create_text_message(f"❌保存临时文件失败：{e}\n")
                        return

                    extract_dir = tmp_dir / "extracted"
                    try:
                        _safe_extract_zip(zip_path, extract_dir)
                    except Exception as e:
                        yield self.create_text_message(f"❌解压失败：{e}\n")
                        return

                    skill_folders = _find_skill_folders(extract_dir)
                    if not skill_folders:
                        yield self.create_text_message("❌压缩包内未找到技能目录（应包含 SKILL.md）。\n")
                        return

                    for folder in skill_folders:
                        target = skills_dir / folder.name
                        if target.exists():
                            yield self.create_text_message(f"❌技能已存在：{folder.name}（请先删除同名技能）\n")
                            return
                        try:
                            shutil.move(str(folder), str(target))
                            installed.append(target.name)
                        except Exception as e:
                            yield self.create_text_message(f"❌安装技能失败：{e}\n")
                            return

            yield self.create_text_message("✅技能已安装：\n" + "\n".join(installed) + "\n")
            skills = list_skills_sorted()
            lines = [f"{idx + 1}. {p.name}" for idx, p in enumerate(skills)]
            yield self.create_text_message("👓当前技能列表：\n" + ("\n".join(lines) if lines else "（空）\n"))
            return

        m_del = re.match(r"^删除技能(\d+)$", command)
        if m_del:
            idx = int(m_del.group(1))
            skills = list_skills_sorted()
            if idx < 1 or idx > len(skills):
                yield self.create_text_message("❌技能序号无效或超出范围。请先使用“查看技能”确认序号。\n")
                return
            target = skills[idx - 1]
            try:
                shutil.rmtree(target, ignore_errors=False)
            except Exception as e:
                yield self.create_text_message(f"❌删除失败：{e}\n")
                return
            yield self.create_text_message(f"✅已删除技能{idx}：{target.name}\n")
            skills = list_skills_sorted()
            if not skills:
                yield self.create_text_message("😑当前技能列表为空。\n")
            else:
                lines = [f"{i + 1}. {p.name}" for i, p in enumerate(skills)]
                yield self.create_text_message("👓当前技能列表：\n" + "\n".join(lines))
            return

        m_dl = re.match(r"^下载技能(\d+)$", command)
        if m_dl:
            idx = int(m_dl.group(1))
            skills = list_skills_sorted()
            if idx < 1 or idx > len(skills):
                yield self.create_text_message("❌技能序号无效或超出范围。请先使用“查看技能”确认序号。\n")
                return
            target = skills[idx - 1]

            try:
                with tempfile.TemporaryDirectory(prefix="skill-zip-") as td:
                    tmp_dir = Path(td)
                    zip_path = tmp_dir / f"{target.name}.zip"
                    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=target.parent, base_dir=target.name)
                    blob = zip_path.read_bytes()
            except Exception as e:
                yield self.create_text_message(f"❌读取文件失败：{e}\n")
                return

            mime_type, _ = mimetypes.guess_type(f"{target.name}.zip")
            if not mime_type:
                mime_type = "application/zip"

            yield self.create_text_message(f"⬇️开始下载技能{idx}：{target.name}.zip\n")
            yield self.create_blob_message(
                blob=blob,
                meta={
                    "mime_type": mime_type,
                    "filename": f"{target.name}.zip",
                },
            )
            return

        yield self.create_text_message("😑未识别的技能管理命令。支持：查看技能、新增技能、删除技能N、下载技能N。\n")
        return
