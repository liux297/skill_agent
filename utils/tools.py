from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
import uuid
from typing import Any, TypeVar
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def _safe_get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    try:
        return obj[key]  # type: ignore[index]
    except Exception:
        pass
    try:
        return getattr(obj, key)
    except Exception:
        return None

def _shorten_text(value: Any, max_len: int = 500) -> str:
    try:
        s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    except Exception:
        s = str(value)
    s = s.replace("\r", "\\r").replace("\n", "\\n")
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."

def _guess_mime_type(filename: str) -> str:
    name = (filename or "").strip().lower()
    _, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext:
        overrides = {
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".csv": "text/csv",
            ".json": "application/json",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".htm": "text/html",
            ".pdf": "application/pdf",
            ".zip": "application/zip",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".yaml": "application/yaml",
            ".yml": "application/yaml",
        }
        if ext in overrides:
            return overrides[ext]
    mime_type, _ = mimetypes.guess_type(name, strict=False)
    return mime_type or "application/octet-stream"

def _safe_join(root: str, relative_path: str) -> str:
    root_abs = os.path.abspath(root)
    joined = os.path.abspath(os.path.join(root_abs, relative_path))
    if os.path.commonpath([root_abs, joined]) != root_abs:
        raise ValueError("path is outside root")
    return joined

def _read_text(path: str, max_chars: int = 12000) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read(max_chars)


def _list_dir(root: str, max_depth: int = 2) -> list[dict[str, Any]]:
    root_abs = os.path.abspath(root)
    entries: list[dict[str, Any]] = []
    root_depth = root_abs.count(os.sep)
    for current_root, dirs, files in os.walk(root_abs):
        depth = current_root.count(os.sep) - root_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        for name in sorted(dirs):
            entries.append(
                {
                    "type": "dir",
                    "path": os.path.join(current_root, name),
                    "relative_path": os.path.relpath(os.path.join(current_root, name), root_abs),
                }
            )
        for name in sorted(files):
            entries.append(
                {
                    "type": "file",
                    "path": os.path.join(current_root, name),
                    "relative_path": os.path.relpath(os.path.join(current_root, name), root_abs),
                }
            )
    return entries


def _parse_frontmatter(content: str) -> dict[str, str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            data[key] = value
    return data

def _extract_first_json_object(text: str) -> str | None:
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```"):
            s = "\n".join(lines[1:-1]).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth_brace = 0  # {} 深度
    depth_bracket = 0  # [] 深度
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth_brace += 1
            continue
        if ch == "}":
            depth_brace -= 1
            if depth_brace == 0 and depth_bracket == 0:
                return s[start : i + 1]
            continue
        if ch == "[":
            depth_bracket += 1
            continue
        if ch == "]":
            depth_bracket -= 1
            continue
    return None

def _normalize_small_reply(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.strip().lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[。．\.，,！!？\?；;：:\-—_~`'\"]+", "", t)
    return t

def _is_allow_reply(text: str) -> bool:
    t = _normalize_small_reply(text)
    if not t:
        return False
    if any(x in t for x in ("不允许", "不同意", "不可以", "不要", "拒绝", "取消")):
        return False
    if t in {"允许", "同意", "可以", "好的", "好", "ok", "okay", "yes", "y", "sure"}:
        return True
    if "允许" in t or "同意" in t:
        return True
    return False

def _is_deny_reply(text: str) -> bool:
    t = _normalize_small_reply(text)
    if not t:
        return False
    return any(x in t for x in ("不允许", "不同意", "不可以", "不要", "拒绝", "取消"))

def _coerce_content_item_to_dict(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None
    if isinstance(item, dict):
        return item
    try:
        dumped = item.model_dump()  # type: ignore[attr-defined]
        if isinstance(dumped, dict):
            return dumped
    except Exception:
        pass
    try:
        item_type = getattr(item, "type", None)
        if item_type:
            result: dict[str, Any] = {"type": item_type}
            for k in ("data", "format", "base64_data", "url", "mime_type", "filename", "detail"):
                v = getattr(item, k, None)
                if v not in (None, ""):
                    result[k] = v
            return result
    except Exception:
        pass
    return None

def _split_message_content(content: Any) -> tuple[str, list[dict[str, Any]]]:
    if content is None:
        return "", []
    if isinstance(content, str):
        return content, []
    if isinstance(content, list) or isinstance(content, tuple):
        text_parts: list[str] = []
        nontext_parts: list[dict[str, Any]] = []
        for item in content:
            item_dict = _coerce_content_item_to_dict(item)
            if not item_dict:
                continue
            item_type = item_dict.get("type")
            if item_type == "text":
                data = item_dict.get("data")
                if isinstance(data, str) and data:
                    text_parts.append(data)
            else:
                nontext_parts.append(item_dict)
        return "".join(text_parts), nontext_parts
    return "", [{"type": "unknown", "value": str(content)}]

def _extract_tool_calls(response: Any) -> list[Any]:
    message = _safe_get(response, "message") or response
    tool_calls = _safe_get(message, "tool_calls") or []
    if isinstance(tool_calls, list):
        return tool_calls
    return []

def _parse_tool_call(tool_call: Any) -> tuple[str | None, str | None, dict[str, Any]]:
    call_id = _safe_get(tool_call, "id")
    function_info = _safe_get(tool_call, "function") or {}
    name = _safe_get(function_info, "name")
    raw_args = _safe_get(function_info, "arguments") or "{}"
    if isinstance(raw_args, dict):
        return call_id, name, raw_args
    if not isinstance(raw_args, str):
        try:
            print(
                "[skill][debug] tool_call_arguments_invalid_type "
                + _shorten_text(
                    {
                        "id": call_id,
                        "name": name,
                        "type": type(raw_args).__name__,
                        "raw": raw_args,
                    },
                    400,
                ),
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass
        return call_id, name, {}
    try:
        parsed = json.loads(raw_args)
        return call_id, name, parsed if isinstance(parsed, dict) else {}
    except Exception as e:
        try:
            print(
                "[skill][debug] tool_call_arguments_json_parse_failed "
                + _shorten_text(
                    {
                        "id": call_id,
                        "name": name,
                        "raw_args": raw_args,
                        "exception": str(e),
                    },
                    400,
                ),
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass
        return call_id, name, {"_raw_args_fallback": raw_args}

def _detect_model_supports_fc(model_config: Any) -> bool:
    """检测模型是否支持 function calling。
    
    参考 Hermes 三种 API 模式适配：通过 model_config 的 provider/mode 字段判断。
    已知不支持 FC 的模型/模式返回 False，其余默认返回 True（乐观假设）。
    """
    if model_config is None:
        return True
    provider = None
    mode = None
    model_name = ""
    if isinstance(model_config, dict):
        provider = str(model_config.get("provider") or "").lower()
        mode = str(model_config.get("mode") or "").lower()
        model_name = str(model_config.get("model") or "").lower()
    else:
        provider = str(_safe_get(model_config, "provider") or "").lower()
        mode = str(_safe_get(model_config, "mode") or "").lower()
        model_name = str(_safe_get(model_config, "model") or "").lower()

    # mode 字段明确指示：chat/completion 模式通常支持 FC
    # 某些 mode 值（如 "text"、"generate"）明确不支持
    if mode in ("text", "generate", "completion"):
        return False

    # 已知不支持 FC 的模型名称模式（小模型通常 FC 能力差）
    _no_fc_patterns = (
        "qwen1.5-0.5b", "qwen1.5-1.8b", "qwen2-0.5b", "qwen2-1.5b",
        "llama-3.2-1b", "llama-3.2-3b", "gemma-2b", "gemma-2-2b",
        "phi-1", "phi-1.5", "tinyllama", "minicpm",
    )
    for pattern in _no_fc_patterns:
        if pattern in model_name:
            return False

    return True


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量。
    
    参考 Hermes 上下文管理：中文约 1.5 字符/token，英文约 4 字符/token。
    混合文本取中间值 2 字符/token 作为粗略估算。
    """
    if not text:
        return 0
    # 统计中文字符数
    cn_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    other_chars = len(text) - cn_chars
    # 中文 1.5 字符/token，其他 4 字符/token
    return int(cn_chars / 1.5) + int(other_chars / 4) + 1


PromptToolT = TypeVar("PromptToolT")

_PROMPT_MESSAGE_TOOLS: list[Any] | None = None
_PROMPT_MESSAGE_TOOLS_CACHE_KEY: tuple[int, int] | None = None


def _build_prompt_message_tools(tool_schemas: list[dict[str, Any]], tool_cls: type[PromptToolT]) -> list[PromptToolT]:
    global _PROMPT_MESSAGE_TOOLS, _PROMPT_MESSAGE_TOOLS_CACHE_KEY

    cache_key = (id(tool_schemas), id(tool_cls))
    if _PROMPT_MESSAGE_TOOLS is not None and _PROMPT_MESSAGE_TOOLS_CACHE_KEY == cache_key:
        return _PROMPT_MESSAGE_TOOLS  # type: ignore[return-value]

    tools: list[PromptToolT] = []
    for schema in tool_schemas:
        if not isinstance(schema, dict):
            continue
        function_info = schema.get("function")
        if not isinstance(function_info, dict):
            continue
        name = function_info.get("name")
        description = function_info.get("description")
        parameters = function_info.get("parameters")
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(description, str):
            description = ""
        if not isinstance(parameters, dict):
            parameters = {}
        if "type" not in parameters:
            parameters["type"] = "object"
        if "properties" not in parameters or not isinstance(parameters.get("properties"), dict):
            parameters["properties"] = {}
        if "required" not in parameters or not isinstance(parameters.get("required"), list):
            parameters["required"] = []
        tools.append(tool_cls(name=name.strip(), description=description, parameters=parameters))

    _PROMPT_MESSAGE_TOOLS = tools  # type: ignore[assignment]
    _PROMPT_MESSAGE_TOOLS_CACHE_KEY = cache_key
    return tools

def _extract_url_and_name(file_item: Any) -> tuple[str | None, str | None]:
    url = None
    name = None
    if hasattr(file_item, "url"):
        url = getattr(file_item, "url", None)
    if hasattr(file_item, "filename"):
        name = getattr(file_item, "filename", None)
    if hasattr(file_item, "name") and not name:
        name = getattr(file_item, "name", None)
    if isinstance(file_item, dict):
        url = file_item.get("url", url)
        name = file_item.get("filename", name) or file_item.get("name", name)
    return url, name

def _infer_ext_from_url(url: str) -> str:
    path = urlparse(url or "").path
    _, ext = os.path.splitext(path)
    return ext if ext else ""

def _safe_filename(preferred_name: str | None, fallback_ext: str = "") -> str:
    if preferred_name:
        base = os.path.basename(str(preferred_name))
        base = re.sub(r"[<>:\"/\\\\|?*]+", "_", base).strip()
        if base:
            return base
    return f"{uuid.uuid4().hex}{fallback_ext}"

def _download_file_content(url: str, timeout: int = 30) -> bytes:
    req = Request(url, headers={"User-Agent": "dify-plugin-skill/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()
