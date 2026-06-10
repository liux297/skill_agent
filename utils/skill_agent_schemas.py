from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_skill_metadata",
            "description": "读取指定技能包的SKILL.md与元数据",
            "parameters": {
                "type": "object",
                "properties": {"skill_name": {"type": "string"}},
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skill_files",
            "description": "列出指定技能包内的文件结构",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 2},
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill_file",
            "description": "读取技能包内的文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "relative_path": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 12000},
                },
                "required": ["skill_name", "relative_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_skill_command",
            "description": "在技能包目录内执行命令（限定可执行程序）",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "cwd_relative": {"type": "string"},
                    "auto_install": {"type": "boolean", "default": False},
                },
                "required": ["skill_name", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_session_context",
            "description": "获取本次会话的技能目录与临时目录信息",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_temp_file",
            "description": "将文本写入 temp 会话目录（相对路径）",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string", "minLength": 1},
                    "content": {"type": "string"},
                },
                "required": ["relative_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_temp_file",
            "description": "读取 temp 会话目录文件内容（相对路径）",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string", "minLength": 1},
                    "max_chars": {"type": "integer", "default": 12000},
                },
                "required": ["relative_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_temp_files",
            "description": "列出 temp 会话目录文件结构",
            "parameters": {
                "type": "object",
                "properties": {"max_depth": {"type": "integer", "default": 4}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_temp_command",
            "description": "在 temp 会话目录内执行命令（限定可执行程序）",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "array", "items": {"type": "string"}},
                    "cwd_relative": {"type": "string"},
                    "auto_install": {"type": "boolean", "default": False},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_temp_file",
            "description": "标记 temp 会话文件为最终交付文件（不复制）",
            "parameters": {
                "type": "object",
                "properties": {
                    "temp_relative_path": {"type": "string", "minLength": 1},
                    "workspace_relative_path": {"type": "string", "minLength": 1},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["temp_relative_path", "workspace_relative_path"],
            },
        },
    },
    # --- 技能管理工具（安装/查看/删除/更新） ---
    {
        "type": "function",
        "function": {
            "name": "install_skill",
            "description": (
                "将 session_dir 下已解压的技能目录或 zip 压缩包安装到 skills_root，使其成为可用技能。"
                "source_path 支持：已解压的目录路径（如 uploads/flow-assistant-skill-master）或 zip 文件路径。"
                "skill_name 为安装后的技能名称（即 skills_root 下的子目录名）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string", "description": "session_dir 下待安装的目录或 zip 文件相对路径"},
                    "skill_name": {"type": "string", "description": "安装后的技能名称（skills_root 下的子目录名）"},
                },
                "required": ["source_path", "skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_installed_skills",
            "description": "列出 skills_root 下所有已安装的技能，包括名称、描述、是否有 SKILL.md 等信息。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "uninstall_skill",
            "description": "按技能名称从 skills_root 中删除已安装的技能。删除后该技能不再可用。",
            "parameters": {
                "type": "object",
                "properties": {"skill_name": {"type": "string"}},
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_skill",
            "description": (
                "按技能名称用新的源文件覆盖更新已安装的技能。"
                "先删除旧版本，再从 source_path（目录或 zip）重新安装。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "要更新的已有技能名称"},
                    "source_path": {"type": "string", "description": "session_dir 下新的目录或 zip 文件相对路径"},
                },
                "required": ["skill_name", "source_path"],
            },
        },
    },
]


def _coerce_command_to_list(arguments: dict) -> dict:
    """如果 command 是字符串，自动拆分为数组，并清理参数中 LLM 从 Markdown 复制时带入的反引号。"""
    cmd = arguments.get("command")
    if isinstance(cmd, str) and cmd.strip():
        import shlex
        arguments["command"] = shlex.split(cmd.strip())
    # 清理每个参数首尾的反引号（LLM 从 Markdown 代码块复制命令时容易带入）
    cmd_list = arguments.get("command")
    if isinstance(cmd_list, list):
        arguments["command"] = [arg.strip("`") for arg in cmd_list]
    return arguments


def _validate_tool_arguments(tool_name: str, arguments: Any) -> tuple[bool, str]:
    if not isinstance(arguments, dict):
        return False, "arguments 必须是对象(dict)"

    # 自动将字符串 command 转为数组
    arguments = _coerce_command_to_list(arguments)

    required: dict[str, list[str]] = {
        "get_skill_metadata": ["skill_name"],
        "list_skill_files": ["skill_name"],
        "read_skill_file": ["skill_name", "relative_path"],
        "run_skill_command": ["skill_name", "command"],
        "get_session_context": [],
        "write_temp_file": ["relative_path", "content"],
        "read_temp_file": ["relative_path"],
        "list_temp_files": [],
        "run_temp_command": ["command"],
        "export_temp_file": ["temp_relative_path", "workspace_relative_path"],
        # 技能管理工具
        "install_skill": ["source_path", "skill_name"],
        "list_installed_skills": [],
        "uninstall_skill": ["skill_name"],
        "update_skill": ["skill_name", "source_path"],
    }

    if tool_name not in required:
        return True, ""

    missing: list[str] = []
    for key in required[tool_name]:
        val = arguments.get(key)
        if val is None:
            missing.append(key)
            continue
        if isinstance(val, str) and not val.strip():
            missing.append(key)
            continue
        if key == "command" and (not isinstance(val, list) or not val):
            missing.append(key)
            continue

    if missing:
        return False, "缺少或为空的必填参数: " + ", ".join(missing)
    return True, ""


def _tool_call_retry_prompt(tool_name: str, detail: str) -> str:
    return (
        f"你刚才发起的工具调用 `{tool_name}` 参数不合法：{detail}。"
        "请严格按工具 schema 重新发起调用（arguments 必须包含必填字段且非空）。"
    )
