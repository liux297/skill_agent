from __future__ import annotations

import sys
from typing import Any

from utils.tools import _safe_get


def _dbg(msg: str) -> None:
    """输出调试日志到 stderr，避免被 plugin_daemon 的 stdio 协议误判为非法 JSON。"""
    try:
        print(f"[skill][debug] {msg}", file=sys.stderr, flush=True)
    except Exception:
        return


def _model_brief(model_config: Any) -> str:
    if isinstance(model_config, dict):
        provider = model_config.get("provider")
        model = model_config.get("model")
        mode = model_config.get("mode")
        return f"provider={provider!s} model={model!s} mode={mode!s}"
    provider = _safe_get(model_config, "provider")
    model = _safe_get(model_config, "model")
    mode = _safe_get(model_config, "mode")
    return f"provider={provider!s} model={model!s} mode={mode!s}"
