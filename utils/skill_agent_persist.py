"""技能持久化备份/恢复：通过 Dify session.storage 跨插件升级保留技能。

设计：
- 每个 skill_space 独立备份
- 备份粒度：每个技能一个 key（包含所有文件 base64 编码）
- 索引 key 记录所有已备份的技能名称
- 恢复时按索引逐个还原
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from utils.skill_agent_constants import SKILL_BACKUP_DATA_PREFIX, SKILL_BACKUP_INDEX_PREFIX


def _index_key(space: str) -> str:
    return f"{SKILL_BACKUP_INDEX_PREFIX}{space}"


def _data_key(space: str, skill_name: str) -> str:
    return f"{SKILL_BACKUP_DATA_PREFIX}{space}:{skill_name}"


def backup_skill(storage: Any, skill_path: str, skill_space: str) -> dict[str, Any]:
    """备份单个技能目录到 session.storage。

    将技能下所有文件 base64 编码后存入一个 KV key。
    """
    skill_name = os.path.basename(skill_path)
    if not skill_name:
        return {"ok": False, "error": "invalid skill path"}
    files: dict[str, str] = {}
    total_bytes = 0
    try:
        for root, _dirs, filenames in os.walk(skill_path):
            for fname in filenames:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, skill_path)
                try:
                    with open(abs_path, "rb") as f:
                        content = f.read()
                    total_bytes += len(content)
                    # 单技能备份限制 10MB（storage 总量限制 100MB）
                    if total_bytes > 10 * 1024 * 1024:
                        return {"ok": False, "error": "skill too large for backup", "bytes": total_bytes}
                    files[rel_path] = base64.b64encode(content).decode("ascii")
                except Exception:
                    continue
        data = json.dumps({"name": skill_name, "files": files}, ensure_ascii=False)
        storage.set(_data_key(skill_space, skill_name), data.encode("utf-8"))
        # 更新索引
        _add_to_index(storage, skill_space, skill_name)
        return {"ok": True, "skill": skill_name, "files": len(files), "bytes": total_bytes}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def backup_all_skills(storage: Any, skills_dir: str, skill_space: str) -> dict[str, Any]:
    """备份指定空间下的所有技能。"""
    if not os.path.isdir(skills_dir):
        return {"ok": False, "error": "skills dir not found"}
    results: list[dict[str, Any]] = []
    for entry in sorted(os.listdir(skills_dir)):
        entry_path = os.path.join(skills_dir, entry)
        if os.path.isdir(entry_path) and not entry.startswith("."):
            results.append(backup_skill(storage, entry_path, skill_space))
    return {"ok": True, "backed_up": len(results), "details": results}


def restore_skill(storage: Any, skill_name: str, skill_space: str, target_dir: str) -> dict[str, Any]:
    """从 storage 恢复单个技能到 target_dir/<skill_name>/。"""
    try:
        raw = storage.get(_data_key(skill_space, skill_name))
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        files = data.get("files", {})
        if not files:
            return {"ok": False, "error": "no files in backup"}
        skill_dir = os.path.join(target_dir, skill_name)
        os.makedirs(skill_dir, exist_ok=True)
        restored = 0
        for rel_path, b64_content in files.items():
            abs_path = os.path.join(skill_dir, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "wb") as f:
                f.write(base64.b64decode(b64_content))
            restored += 1
        return {"ok": True, "skill": skill_name, "files_restored": restored}
    except Exception as e:
        return {"ok": False, "error": str(e), "skill": skill_name}


def restore_all_skills(storage: Any, skill_space: str, target_dir: str) -> dict[str, Any]:
    """从 storage 恢复指定空间的所有技能。

    返回恢复结果摘要。
    """
    index = _get_index(storage, skill_space)
    if not index:
        return {"ok": True, "restored": 0, "message": "no backup found"}
    os.makedirs(target_dir, exist_ok=True)
    restored = 0
    errors: list[str] = []
    for skill_name in index:
        result = restore_skill(storage, skill_name, skill_space, target_dir)
        if result.get("ok"):
            restored += 1
        else:
            errors.append(f"{skill_name}: {result.get('error', 'unknown')}")
    return {
        "ok": True,
        "restored": restored,
        "total_in_backup": len(index),
        "errors": errors,
    }


def remove_skill_backup(storage: Any, skill_name: str, skill_space: str) -> None:
    """删除单个技能的备份。"""
    try:
        storage.delete(_data_key(skill_space, skill_name))
    except Exception:
        pass
    _remove_from_index(storage, skill_space, skill_name)


def clear_skill_backups(storage: Any, skill_space: str) -> None:
    """清除指定空间的所有备份。"""
    for name in _get_index(storage, skill_space):
        try:
            storage.delete(_data_key(skill_space, name))
        except Exception:
            pass
    try:
        storage.delete(_index_key(skill_space))
    except Exception:
        pass


# ==================== 索引操作 ====================

def _get_index(storage: Any, skill_space: str) -> list[str]:
    try:
        raw = storage.get(_index_key(skill_space))
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _set_index(storage: Any, skill_space: str, names: list[str]) -> None:
    try:
        storage.set(_index_key(skill_space), json.dumps(names).encode("utf-8"))
    except Exception:
        pass


def _add_to_index(storage: Any, skill_space: str, skill_name: str) -> None:
    names = _get_index(storage, skill_space)
    if skill_name not in names:
        names.append(skill_name)
        _set_index(storage, skill_space, names)


def _remove_from_index(storage: Any, skill_space: str, skill_name: str) -> None:
    names = _get_index(storage, skill_space)
    if skill_name in names:
        names.remove(skill_name)
        _set_index(storage, skill_space, names)
