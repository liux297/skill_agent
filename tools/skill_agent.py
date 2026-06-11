import re
import json
import os
import time
import uuid
import base64
import hashlib
from collections.abc import Generator
from typing import Any

from utils.tools import (
    _build_prompt_message_tools,
    _download_file_content,
    _extract_first_json_object,
    _extract_url_and_name,
    _guess_mime_type,
    _infer_ext_from_url,
    _is_allow_reply,
    _is_deny_reply,
    _list_dir,
    _parse_tool_call,
    _safe_filename,
    _safe_get,
    _safe_join,
    _shorten_text,
    _split_message_content,
 )

from utils.skill_agent_constants import HISTORY_TRANSCRIPT_MAX_CHARS
from utils.skill_agent_debug import _dbg, _model_brief
from utils.skill_agent_exec import _cleanup_old_temp_sessions, _detect_skills_root
from utils.skill_agent_runtime import _AgentRuntime
from utils.skill_agent_schemas import TOOL_SCHEMAS, _coerce_command_to_list, _tool_call_retry_prompt, _validate_tool_arguments
from utils.skill_agent_storage import (
    _append_history_turn,
    _get_history_storage_key,
    _get_resume_storage_key,
    _get_session_dir_storage_key,
    _storage_get_json,
    _storage_get_text,
    _storage_set_json,
    _storage_set_text,
)
from utils.skill_agent_uploads import _build_uploads_context

from dify_plugin import Tool
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.entities.tool import ToolInvokeMessage

class SkillAgentTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        model = tool_parameters.get("model")
        query = tool_parameters.get("query")
        max_steps = int(tool_parameters.get("max_steps") or 8)
        memory_turns = int(tool_parameters.get("memory_turns") or 10)
        history_turns = int(tool_parameters.get("history_turns") or 0)
        max_stdout_chars = int(tool_parameters.get("max_stdout_chars") or 30000)
        system_prompt = tool_parameters.get("system_prompt") or "你是一个xxxx"
        # 详细模式开关：控制是否向用户展示工具调用/执行细节（调试时开启，面向用户时可关闭）
        _verbose_raw = tool_parameters.get("verbose")
        verbose = _verbose_raw not in (False, "false", "False", 0, "0")
        skills_root = _detect_skills_root(tool_parameters.get("skills_root"))
        custom_variables_raw = tool_parameters.get("custom_variables") or ""
        custom_variables: dict[str, str] = {}
        if isinstance(custom_variables_raw, str) and custom_variables_raw.strip():
            try:
                parsed = json.loads(custom_variables_raw.strip())
                if isinstance(parsed, dict):
                    custom_variables = {str(k): str(v) for k, v in parsed.items() if v is not None}
            except (json.JSONDecodeError, TypeError):
                custom_variables = {}

        if not query or not isinstance(query, str):
            yield self.create_text_message("❌缺少 query 参数\n")
            return
        user_input = str(query)

        storage = self.session.storage
        resume_key = _get_resume_storage_key(self.session)
        history_key = _get_history_storage_key(self.session)
        session_dir_key = _get_session_dir_storage_key(self.session)
        resume_state = _storage_get_json(storage, resume_key)
        resume_pending = bool(resume_state.get("pending"))
        is_resuming = False

        plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # temp 目录放在插件目录外的持久化路径，避免升级时丢失
        temp_root = os.path.join(os.path.dirname(plugin_root), "skill_agent_data", "temp")
        os.makedirs(temp_root, exist_ok=True)
        persisted_session_dir = _storage_get_text(storage, session_dir_key).strip()
        if persisted_session_dir and os.path.isdir(persisted_session_dir):
            session_dir = persisted_session_dir
        else:
            session_dir = os.path.join(temp_root, f"dify-skill-{uuid.uuid4().hex[:8]}")
        resume_context = ""

        if resume_pending and _is_deny_reply(user_input):
            _storage_set_json(storage, resume_key, None)
            yield self.create_text_message("🤝已收到你的拒绝，本次不会在 temp 目录创建脚本继续执行。\n")
            return
        if resume_pending and _is_allow_reply(user_input):
            candidate = str(resume_state.get("session_dir") or "").strip()
            if candidate:
                session_dir = candidate
                os.makedirs(session_dir, exist_ok=True)
                _storage_set_text(storage, session_dir_key, session_dir)
                original_query_for_resume = str(resume_state.get("original_query") or "").strip()
                if original_query_for_resume:
                    query = original_query_for_resume
                is_resuming = True
                _storage_set_json(storage, resume_key, None)
                resume_context = (
                    "\n\n[续跑授权]\n"
                    + "用户已明确允许你在 temp 会话目录中自行创建脚本、必要时安装依赖，并继续上一轮未完成的生成。\n"
                    + "请直接基于当前 temp 会话目录中的中间产物继续推进，优先生成最终可交付文件。\n"
                )
        os.makedirs(session_dir, exist_ok=True)
        _storage_set_text(storage, session_dir_key, session_dir)
        if not is_resuming:
            _cleanup_old_temp_sessions(temp_root, keep=4, protect_dirs={session_dir})

        file_items: list[Any] = []
        files_param = tool_parameters.get("files")
        if isinstance(files_param, list):
            file_items = [x for x in files_param if x]
        elif files_param:
            file_items = [files_param]
        elif tool_parameters.get("file"):
            file_items = [tool_parameters.get("file")]

        uploads_context = ""
        if file_items:
            uploads_dir = _safe_join(session_dir, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            uploaded: list[dict[str, Any]] = []
            for item in file_items:
                url, name = _extract_url_and_name(item)
                if not url:
                    yield self.create_text_message("❌未能获取上传文件 URL（files[i].url）。\n")
                    return
                try:
                    content = _download_file_content(str(url), timeout=45)
                except Exception as e:
                    yield self.create_text_message(f"❌文件下载失败：{str(e)}\n")
                    return
                ext = _infer_ext_from_url(str(url))
                filename = _safe_filename(str(name) if name else None, fallback_ext=ext)
                abs_path = os.path.join(uploads_dir, filename)
                try:
                    with open(abs_path, "wb") as f:
                        f.write(content)
                except Exception as e:
                    yield self.create_text_message(f"❌保存上传文件失败：{str(e)}\n")
                    return

                rel_path = f"uploads/{filename}"
                mime = None
                if isinstance(item, dict) and item.get("mime_type"):
                    mime = str(item.get("mime_type") or "").strip() or None
                if not mime:
                    try:
                        mime = _guess_mime_type(filename)
                    except Exception:
                        mime = None
                uploaded.append(
                    {
                        "relative_path": rel_path,
                        "bytes": len(content),
                        "mime_type": mime or "",
                        "filename": filename,
                        "source_url": str(url),
                    }
                )

            lines = ["\n\n[上传文件清单]", "以下路径均相对于本次会话的 session_dir："]
            for f in uploaded:
                lines.append(
                    f"- {f.get('relative_path')} | mime={f.get('mime_type') or ''} | bytes={f.get('bytes') or 0} | filename={f.get('filename') or ''}"
                )
            uploads_context = "\n".join(lines) + "\n"
        else:
            uploads_dir = _safe_join(session_dir, "uploads")
            os.makedirs(uploads_dir, exist_ok=True)

        # 仅在前面未构建上传文件清单时，才从磁盘扫描补充
        if not uploads_context:
            uploads_context = _build_uploads_context(session_dir)

        runtime = _AgentRuntime(
            skills_root=skills_root,
            session_dir=session_dir,
            max_steps=max_steps,
            memory_turns=memory_turns,
            custom_variables=custom_variables,
            max_stdout_chars=max_stdout_chars,
        )

        history_messages: list[Any] = []
        if history_turns > 0:
            history_state = _storage_get_json(storage, history_key)
            turns = history_state.get("turns")
            if isinstance(turns, list) and turns:
                picked: list[tuple[str, str]] = []
                for t in reversed(turns[-history_turns:]):
                    if not isinstance(t, dict):
                        continue
                    u = str(t.get("user") or "").strip()
                    a = str(t.get("assistant") or "").strip()
                    if not u and not a:
                        continue
                    picked.append((u, a))
                if picked:
                    acc: list[tuple[str, str]] = []
                    total = 0
                    for u, a in picked:
                        block_len = len(u) + len(a)
                        if total + block_len > HISTORY_TRANSCRIPT_MAX_CHARS and acc:
                            break
                        acc.append((u, a))
                        total += block_len
                        if total >= HISTORY_TRANSCRIPT_MAX_CHARS:
                            break
                    acc.reverse()
                    for u, a in acc:
                        if u:
                            history_messages.append(UserPromptMessage(content=u))
                        if a:
                            history_messages.append(AssistantPromptMessage(content=a))

        skills_index = runtime.load_skills_index()
        try:
            skills_count = len(skills_index.get("skills") or []) if isinstance(skills_index, dict) else 0
        except Exception:
            skills_count = 0
        _dbg(
            "start "
            + _model_brief(model)
            + f" session_dir={session_dir} skills_root={skills_root!s} skills_count={skills_count} "
            + f"query_len={len(query)}"
        )
        system_content = (
            system_prompt.strip()
            + "\n\n你是一个使用 Skills 文件夹作为“工具箱”的通用型 Agent。\n"
            + "\n[会话路径]\n"
            + f"- session_dir: {session_dir}\n"
            + f"- skills_root: {skills_root}\n"
            + (
                "\n[自定义变量]\n"
                + "以下变量由调用方注入，技能可通过 get_session_context 获取，在执行命令时可以作为参数引用：\n"
                + "\n".join(f"- {k}: {v}" for k, v in custom_variables.items()) + "\n"
                if custom_variables else ""
            )
            + "你必须遵循渐进式披露流程：\n"
            + "1) 只根据技能元数据（name/description）判断可能相关的技能\n"
            + "2) 触发时才调用 get_skill_metadata 读取 SKILL.md（说明文档）\n"
            + "3) 任何对技能的进一步操作（list_skill_files/read_skill_file/run_skill_command）之前，必须先 get_skill_metadata；若未执行，本系统会拒绝该调用并要求你先补读说明书。\n"
            + "4) 如果 SKILL.md 中已经明确给出了要执行的脚本路径和参数格式，你可以直接调用 run_skill_command 执行，无需再 list_skill_files 或 read_skill_file 确认。只有当说明文档没有明确脚本路径时，才需要先 list_skill_files 查看目录结构。\n"
            + "5) 只有在需要更深信息时，才调用 read_skill_file\n"
            + "6) 只有在明确需要执行脚本/命令时，才调用 run_skill_command\n"
            + "7) 如果 SKILL.md 已明确给出可执行入口，直接执行即可；如果缺少可执行入口，则先交付当前可交付产物，并询问用户是否允许你在 temp 目录中自行创建脚本后再尝试生成。\n"
            + "8) 按说明书要求生成最终文件后，必须用 export_temp_file 标记最终文件\n"
            + "路径规则：uploads/ 与你用 write_temp_file 生成的中间产物都位于 session_dir 下；run_skill_command 的 cwd 在 skills_root/<skill_name> 下。\n"
            + "因此：只要命令参数需要引用 uploads/ 或 temp 中间文件，一律使用 read_temp_file 返回的绝对路径（result.path）传给命令；不要使用 ../uploads、../../temp 这类相对路径猜测。\n"
            + "依赖安装规则：如需 npm install/npm ci/bun install，必须用 run_skill_command 在技能包内含 package.json 的目录执行（通过 cwd_relative 指到该目录）；禁止在 session_dir 执行 install，否则会写入 temp/<session>/node_modules 导致每次会话重复安装。\n"
            + "补充规则1：如果用户请求中已经明确给出具体类型/参数，则视为已确认，不要重复追问，直接进入对应分支执行。\n"
            + "补充规则2：禁止主动追问。当用户输入存在明显错别字或表述不清时，你应该自主推断其真实意图并直接执行，而不是反问用户。只有当用户意图完全无法推断、且缺少该信息确实无法继续时，才允许追问。追问时：本轮只输出问题，立刻结束，不得继续执行任何操作。\n"
            + "补充规则3：默认值只能在用户明确说‘默认/随便/你决定’时启用；用户未回复不等于选择了默认。"
            + "补充规则4：当你准备调用 write_temp_file 时，必须先在自然语言里输出一行“写入意图确认”，包含：relative_path + 内容摘要（前 80 字）+ 大致长度；然后再发起工具调用。relative_path 必须是文件路径（不能是空、'.'、'..'、不能以 '/' 结尾，不能指向目录）。\n"
            + "补充规则5：如果收到的命令执行结果（stdout）是 JSON 格式，你必须将其转换为结构化的中文自然语言摘要（如表格、列表等），禁止直接输出原始 JSON。关键：你必须严格使用 API 返回的真实数据，禁止编造、修改或美化数据。如果数据被截断，只展示已获取的部分并注明'数据可能不完整'。\n"
            + "补充规则6（最小化中间确认原则）：在处理用户请求的全过程中，绝对禁止不必要的中间确认和询问。遇到以下情况必须直接执行而不是追问：(1) 用户输入有错别字但意图明确（如'安些'='哪些'）；(2) 请求简短但结合技能索引可以推断意图；(3) 任何可以通过自主判断解决的问题。只有删除用户数据、执行不可逆操作等真正关键决策点才允许暂停确认。\n"
            + "补充规则7（禁止输出裸命令）：绝对禁止将 curl、bash、python 等原始命令作为文本输出给用户。所有命令执行必须通过 run_skill_command 或 run_temp_command 工具调用。即使 SKILL.md 中包含 curl 示例，你也必须将其转换为 run_skill_command 工具调用来执行，而不是输出 curl 命令文本。\n"
            + "补充规则8（必须完成到最终结果）：你必须持续推进直到获得最终结果并用业务语言回复用户。绝对禁止在以下情况停止：(1) 刚调用完工具但还未处理返回数据；(2) 已拿到 API 数据但还未转换为用户可理解的业务回复；(3) 任何中间步骤。只有当你已经用业务语言向用户给出了完整的最终回答后，才可以结束。\n"
            + "补充规则9：技能管理流程——当用户上传技能压缩包（zip）并要求添加/安装技能时，请按以下步骤执行：\n"
            + "  (1) 如果上传的是 zip 文件且尚未解压，先用 run_temp_command 执行 unzip 解压到 session_dir\n"
            + "  (2) 调用 install_skill(source_path=解压后目录或zip路径, skill_name=用户指定的名称) 安装到 skills_root\n"
            + "  (3) 安装成功后即可通过 get_skill_metadata / list_skill_files 等工具使用该技能\n"
            + "  (4) 如需查看已安装的全部技能，调用 list_installed_skills()\n"
            + "  (5) 如需删除技能，调用 uninstall_skill(skill_name)\n"
            + "  (6) 如需更新已有技能，调用 update_skill(skill_name, source_path)，source_path 为新的 zip 或解压目录\n"
            + (uploads_context or "")
            + "你必须把实现过程中的中间产物写入 temp 会话目录（脚本、草稿、生成物等）：\n"
            + "- 写文本：write_temp_file\n"
            + "- 运行命令生成文件：run_temp_command\n"
            + "对任何“有明确交付物”的请求，你必须在同一轮内推进直到：生成可交付文件，或给出明确失败原因。\n"
            + "只有调用 export_temp_file 标记的文件，才会作为最终交付文件返回给用户；uploads/ 与未标记文件不会回传。\n\n"
            + "可用动作：\n"
            + "- get_session_context()\n"
            + "- get_skill_metadata(skill_name)\n"
            + "- list_skill_files(skill_name, max_depth)\n"
            + "- read_skill_file(skill_name, relative_path, max_chars)\n"
            + "- run_skill_command(skill_name, command, cwd_relative, auto_install)\n"
            + "- write_temp_file(relative_path, content)\n"
            + "- read_temp_file(relative_path, max_chars)\n"
            + "- list_temp_files(max_depth)\n"
            + "- run_temp_command(command, cwd_relative, auto_install)\n"
            + "- export_temp_file(temp_relative_path, workspace_relative_path, overwrite)  # 不复制，仅标记交付名\n"
            + "- install_skill(source_path, skill_name)  # 从上传的 zip/目录安装技能到 skills_root\n"
            + "- list_installed_skills()  # 查看所有已安装技能\n"
            + "- uninstall_skill(skill_name)  # 按名称删除已安装技能\n"
            + "- update_skill(skill_name, source_path)  # 按名称用新 zip/目录覆盖更新技能\n\n"
            + "如果模型支持 function call，请直接发起工具调用；若不支持，则用 JSON 协议响应：\n"
            + '{"type":"tool","name":"get_skill_metadata","arguments":{"skill_name":"xxx"}}\n'
            + '或 {"type":"final","content":"..."}\n\n'
            + "技能索引（用于判断是否需要调用技能）：\n"
            + json.dumps(skills_index, ensure_ascii=False)
            + (resume_context or "")
        )

        messages: list[Any] = [SystemPromptMessage(content=system_content)]
        if history_messages:
            messages.extend(history_messages)
        messages.append(UserPromptMessage(content=query))

        def compact() -> None:
            if memory_turns <= 0:
                return
            keep = 1 + memory_turns * 4
            if len(messages) > keep:
                system_msg = messages[0]
                tail = messages[-(keep - 1) :]
                messages[:] = [system_msg, *tail]

        final_text: str | None = None
        final_file_meta: dict[str, dict[str, str]] = {}
        empty_responses = 0
        tool_result_echo_count = 0  # TOOL_RESULT 回声检测计数，防止无限循环
        saved_asset_fingerprints: set[str] = set()
        resume_saved = False
        final_text_already_streamed = False

        def stream_text_to_user(text: str, chunk_size: int = 8) -> Generator[ToolInvokeMessage]:
            s = (text or "").strip()
            if not s:
                return
            step = max(1, int(chunk_size))
            for i in range(0, len(s), step):
                yield self.create_text_message(s[i : i + step])

        def redact_user_visible_text(text: str) -> str:
            s = str(text or "")
            if not s:
                return s
            # 只脱敏 session_dir 和 skills_root 这两个已知敏感路径
            for p in [session_dir, skills_root]:
                if p and isinstance(p, str):
                    s = s.replace(p, "<REDACTED_PATH>")
                    s = s.replace(p.replace("\\", "/"), "<REDACTED_PATH>")
            return s

        # 工具调用进度消息：verbose 开启时展示细节，关闭时只输出简洁描述
        _tool_step_counter = 0
        _non_verbose_header_emitted = False

        # 数字序号映射（最多 20 步，超出后回退为普通数字）
        _CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

        def _step_label() -> str:
            """返回当前步骤的圆圈数字标签。"""
            idx = _tool_step_counter - 1
            if 0 <= idx < len(_CIRCLED_NUMS):
                return _CIRCLED_NUMS[idx]
            return f"({idx + 1})"

        def emit_tool_progress(tool_name: str, detail: str = "") -> Generator[ToolInvokeMessage]:
            nonlocal _tool_step_counter, _non_verbose_header_emitted
            _tool_step_counter += 1
            label = _step_label()

            if not verbose:
                # ── 非详细模式：按阶段展示简洁标题，避免刷屏 ──
                _phase_map = {
                    "get_skill_metadata": "查阅技能",
                    "list_skill_files": "浏览文件",
                    "read_skill_file": "读取文件",
                    "run_skill_command": "执行命令",
                    "write_temp_file": "写入文件",
                    "read_temp_file": "读取文件",
                    "list_temp_files": "查看文件",
                    "run_temp_command": "执行命令",
                    "export_temp_file": "交付文件",
                    "install_skill": "安装技能",
                    "list_installed_skills": "查看技能",
                    "uninstall_skill": "卸载技能",
                    "update_skill": "更新技能",
                    "get_session_context": "获取上下文",
                }
                phase = _phase_map.get(tool_name, "处理中")
                if not _non_verbose_header_emitted:
                    _non_verbose_header_emitted = True
                    yield self.create_text_message("\n⏳ **正在处理中…**\n")
                yield self.create_text_message(f"  {label} {phase}\n")
                return

            # ── 详细模式：展示分类图标 + 步骤编号 + 操作对象 ──
            _detail_map = {
                "get_skill_metadata": ("🔍", f"查阅技能《{detail}》说明书"),
                "list_skill_files": ("📂", f"浏览技能《{detail}》文件结构"),
                "read_skill_file": ("📄", f"读取文件：{detail}"),
                "run_skill_command": ("⚡", "执行技能命令"),
                "write_temp_file": ("📝", f"写入文件：{detail}"),
                "read_temp_file": ("📖", f"读取临时文件：{detail}"),
                "list_temp_files": ("📋", "查看临时目录"),
                "run_temp_command": ("⚡", "执行临时命令"),
                "export_temp_file": ("📦", f"标记交付文件：{detail}"),
                "install_skill": ("🔧", f"安装技能《{detail}》"),
                "list_installed_skills": ("🔧", "查看已安装技能"),
                "uninstall_skill": ("🗑️", f"卸载技能《{detail}》"),
                "update_skill": ("🔄", f"更新技能《{detail}》"),
                "get_session_context": ("ℹ️", "获取会话上下文"),
            }
            icon, desc = _detail_map.get(tool_name, ("⚙️", f"执行 {tool_name}"))
            yield self.create_text_message(f"{icon} {label} {desc}\n")

        def emit_tool_result(tool_name: str, result: Any) -> Generator[ToolInvokeMessage]:
            """verbose 模式下，工具执行完后展示简短结果摘要。"""
            if not verbose:
                return
            if not isinstance(result, dict):
                return
            # 出错时展示简短错误提示
            err = result.get("error")
            if err:
                yield self.create_text_message(f"  ⚠️ {err}\n")
                return
            # 按工具类型展示关键结果
            if tool_name == "get_skill_metadata":
                skill = result.get("skill", "")
                yield self.create_text_message(f"  ✔️ 已获取《{skill}》说明书\n")
            elif tool_name == "list_skill_files":
                entries = result.get("entries") or []
                yield self.create_text_message(f"  ✔️ 共 {len(entries)} 个文件/目录\n")
            elif tool_name in ("read_skill_file", "read_temp_file"):
                content = result.get("content", "")
                lines = content.count("\n") + 1 if content else 0
                yield self.create_text_message(f"  ✔️ 已读取 {lines} 行\n")
            elif tool_name in ("run_skill_command", "run_temp_command"):
                rc = result.get("returncode")
                stdout = result.get("stdout", "")
                if rc == 0:
                    out_len = len(stdout)
                    yield self.create_text_message(f"  ✔️ 执行成功（输出 {out_len} 字符）\n")
                else:
                    yield self.create_text_message(f"  ❌ 执行失败（返回码 {rc}）\n")
            elif tool_name == "write_temp_file":
                nbytes = result.get("bytes", 0)
                yield self.create_text_message(f"  ✔️ 已写入 {nbytes} 字节\n")
            elif tool_name == "list_temp_files":
                entries = result.get("entries") or []
                yield self.create_text_message(f"  ✔️ 共 {len(entries)} 个文件/目录\n")
            elif tool_name == "export_temp_file":
                name = result.get("requested_name", "")
                yield self.create_text_message(f"  ✔️ 已标记交付：{name}\n")
            elif tool_name == "install_skill":
                skill = result.get("skill", "")
                yield self.create_text_message(f"  ✔️ 技能《{skill}》安装成功\n")
            elif tool_name == "list_installed_skills":
                count = result.get("skills_count", 0)
                yield self.create_text_message(f"  ✔️ 已安装 {count} 个技能\n")
            elif tool_name == "uninstall_skill":
                skill = result.get("skill", "")
                yield self.create_text_message(f"  ✔️ 技能《{skill}》已卸载\n")
            elif tool_name == "update_skill":
                skill = result.get("skill", "")
                yield self.create_text_message(f"  ✔️ 技能《{skill}》已更新\n")

        def persist_llm_assets(parts: Any) -> list[str]:
            if not parts or not isinstance(parts, list):
                return []
            saved: list[str] = []
            out_dir = _safe_join(session_dir, "llm_assets")
            os.makedirs(out_dir, exist_ok=True)
            for i, item in enumerate(parts):
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "")
                if item_type not in {"image", "document", "audio", "video"}:
                    continue
                mime = str(item.get("mime_type") or "")
                filename = str(item.get("filename") or "").strip()
                url = str(item.get("url") or item.get("data") or "").strip()
                b64 = str(item.get("base64_data") or "").strip()
                raw: bytes | None = None
                if b64:
                    try:
                        raw = base64.b64decode(b64, validate=False)
                    except Exception:
                        raw = None
                if raw is None and url.startswith("data:") and ";base64," in url:
                    try:
                        header, payload = url.split(";base64,", 1)
                        if not mime and header.startswith("data:"):
                            mime = header[5:]
                        raw = base64.b64decode(payload, validate=False)
                    except Exception:
                        raw = None
                if raw is None:
                    continue
                try:
                    fp = hashlib.sha1(raw).hexdigest()
                    key = f"{item_type}|{mime}|{fp}"
                except Exception:
                    key = f"{item_type}|{mime}|{len(raw)}"
                if key in saved_asset_fingerprints:
                    continue
                saved_asset_fingerprints.add(key)
                if not filename:
                    ext = ""
                    if mime:
                        if "png" in mime:
                            ext = ".png"
                        elif "jpeg" in mime or "jpg" in mime:
                            ext = ".jpg"
                        elif "pdf" in mime:
                            ext = ".pdf"
                        elif "json" in mime:
                            ext = ".json"
                        elif "text" in mime or "markdown" in mime:
                            ext = ".txt"
                    filename = f"{item_type}-{i+1}{ext or ''}"
                dst = _safe_join(out_dir, filename)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(filename)
                    dst = _safe_join(out_dir, f"{base}-{fp[:8] if 'fp' in locals() else uuid.uuid4().hex[:8]}{ext}")
                try:
                    with open(dst, "wb") as f:
                        f.write(raw)
                    saved.append(os.path.relpath(dst, session_dir))
                except Exception:
                    continue
            return saved

        # "TOOL_RESULT" 的所有前缀（从4字符开始），用于流式输出时检测部分匹配
        _TOOL_RESULT_PREFIXES = tuple("TOOL_RESULT"[:i] for i in range(4, len("TOOL_RESULT") + 1))

        def invoke_llm_live(
            *, prompt_messages: list[Any], tools: list[Any] | None
        ) -> Generator[ToolInvokeMessage, None, tuple[str, list[Any], Any, int, bool]]:
            nontext_content: list[dict[str, Any]] = []
            tool_calls_all: list[Any] = []
            text_parts: list[str] = []
            chunks_count = 0
            streamed_any = False
            saw_tool_calls = False
            typing_chunk = 6
            emitted_prefix = False
            emitted_len = 0

            def emit_typing(text: str) -> Generator[ToolInvokeMessage, None, None]:
                nonlocal streamed_any
                if not text:
                    return
                tagged = "\n【🤖Skill_Agent】\n" + text.strip() + "\n\n"
                step = max(1, int(typing_chunk))
                for i in range(0, len(tagged), step):
                    yield self.create_text_message(tagged[i : i + step])
                    streamed_any = True

            def should_emit_user_text(text: str) -> bool:
                if not text:
                    return False
                s = str(text)
                stripped = s.lstrip()
                # TOOL_RESULT 及其部分前缀（TOOL、TOOL_、TOOL_R 等）是内部协议，不应展示
                if stripped.startswith(_TOOL_RESULT_PREFIXES):
                    return False
                # 以 { 开头但尚未形成完整 JSON，暂不输出（等待更多数据）
                if stripped.startswith("{") and _extract_first_json_object(s) is None:
                    return False
                # 以 ``` 开头但代码块未闭合，暂不输出
                if stripped.startswith("```") and stripped.count("```") < 2:
                    return False
                # 检测完整 JSON 协议响应并抑制展示
                json_text = _extract_first_json_object(text)
                if not json_text:
                    return True
                try:
                    obj = json.loads(json_text)
                except Exception:
                    return True
                if not isinstance(obj, dict):
                    return True
                t = obj.get("type")
                if t in {"tool", "final"}:
                    return False
                # TOOL_RESULT 回声格式：有 name+result 但无 type
                if "name" in obj and "result" in obj and "type" not in obj:
                    return False
                return True

            def _safe_stream_boundary(text: str) -> int:
                """流式输出时，计算可安全输出的文本长度。
                自然语言部分即时输出，遇到可能的 JSON 协议时截断等待。
                """
                # TOOL_RESULT 完整匹配
                tr_pos = text.find("TOOL_RESULT")
                if tr_pos >= 0:
                    return tr_pos
                # TOOL_RESULT 部分前缀匹配（如 "TOOL"、"TOOL_R" 等）
                for prefix in _TOOL_RESULT_PREFIXES:
                    if text.endswith(prefix):
                        return len(text) - len(prefix)
                brace_pos = text.find("{")
                if brace_pos < 0:
                    return len(text)
                # { 之前有自然语言内容，先输出这些
                if brace_pos > 0:
                    return brace_pos
                # 文本以 { 开头，should_emit_user_text 会处理延迟逻辑
                return 0

            try:
                try:
                    response = self.session.model.llm.invoke(
                        model_config=model,
                        prompt_messages=prompt_messages,
                        tools=tools,
                        stream=True,
                    )
                except TypeError:
                    response = self.session.model.llm.invoke(
                        model_config=model,
                        prompt_messages=prompt_messages,
                        stream=True,
                    )

                if _safe_get(response, "message") is not None:
                    msg = _safe_get(response, "message") or {}
                    content = _safe_get(msg, "content")
                    text, parts = _split_message_content(content)
                    if parts:
                        nontext_content.extend(parts)
                    tool_calls = _safe_get(msg, "tool_calls") or []
                    if isinstance(tool_calls, list):
                        tool_calls_all.extend(tool_calls)
                        if tool_calls:
                            saw_tool_calls = True
                    if text:
                        text_parts.append(text)
                    combined_text = "".join(text_parts).strip()
                    if combined_text and not saw_tool_calls and should_emit_user_text(combined_text):
                        yield from emit_typing(combined_text)
                    return combined_text, tool_calls_all, nontext_content, chunks_count, streamed_any

                for chunk in response:
                    chunks_count += 1
                    delta = _safe_get(chunk, "delta") or {}
                    msg = _safe_get(delta, "message") or {}
                    content = _safe_get(msg, "content")
                    t, parts = _split_message_content(content)
                    if parts:
                        nontext_content.extend(parts)
                    tc = _safe_get(msg, "tool_calls") or []
                    if isinstance(tc, list) and tc:
                        tool_calls_all.extend(tc)
                        if not saw_tool_calls:
                            saw_tool_calls = True
                    if t:
                        text_parts.append(t)
                        combined_text_live = "".join(text_parts).strip()
                        if combined_text_live and not saw_tool_calls:
                            # 计算可安全流式输出的文本边界（JSON/TOOL_RESULT 之前的自然语言部分）
                            safe_len = _safe_stream_boundary(combined_text_live)
                            safe_text = combined_text_live[:safe_len] if safe_len > 0 else combined_text_live
                            if safe_text and should_emit_user_text(safe_text):
                                if not emitted_prefix:
                                    yield self.create_text_message("\n【🤖Skill_Agent】\n")
                                    emitted_prefix = True
                                new = safe_text[emitted_len:]
                                if new:
                                    step = max(1, int(typing_chunk))
                                    for i in range(0, len(new), step):
                                        yield self.create_text_message(new[i : i + step])
                                        streamed_any = True
                                emitted_len = len(safe_text)
                combined_text = "".join(text_parts).strip()
                if emitted_prefix:
                    yield self.create_text_message("\n\n")
                elif combined_text and not saw_tool_calls and should_emit_user_text(combined_text):
                    yield from emit_typing(combined_text)
                return combined_text, tool_calls_all, nontext_content, chunks_count, streamed_any
            except Exception as e:
                return "", [], {"error": "stream_parse_failed", "exception": str(e)}, chunks_count, streamed_any

        try:
            for step_idx in range(max_steps):
                compact()
                _dbg(f"step={step_idx+1}/{max_steps} messages={len(messages)}")
                try:
                    res_text, tool_calls, nontext, chunks, streamed_any = yield from invoke_llm_live(
                        prompt_messages=messages,
                        tools=_build_prompt_message_tools(TOOL_SCHEMAS, PromptMessageTool),
                    )
                except Exception as e:
                    msg = str(e)
                    if "NameResolutionError" in msg or "Failed to resolve" in msg:
                        yield self.create_text_message(
                            "❌ LLM 调用失败：无法解析模型服务域名（DNS/网络问题）。\n"
                            "当前报错信息：\n"
                            + msg
                            + "\n\n请检查：\n"
                            + "1) 运行插件的环境是否能访问公网/是否需要代理\n"
                            + "2) DNS 是否可用（能否解析 dashscope.aliyuncs.com 等域名）\n"
                            + "3) Dify 的模型供应商（通义）网络出站是否被限制\n"
                        )
                    else:
                        yield self.create_text_message("❌ LLM 调用失败：\n" + msg)
                    return

                _dbg(
                    f"llm_return content_len={len(res_text)} tool_calls={len(tool_calls)} chunks={chunks} "
                    f"nontext={_shorten_text(nontext, 200) if nontext else ''}"
                )
                if nontext:
                    saved_assets = persist_llm_assets(nontext)
                    if saved_assets:
                        _dbg(f"nontext_assets_saved={len(saved_assets)} paths={_shorten_text(saved_assets, 300)}")
                if tool_calls:
                    empty_responses = 0
                    messages.append(AssistantPromptMessage(content=res_text or "", tool_calls=tool_calls))
                    forced_text: str | None = None
                    for tc in tool_calls:
                        call_id, name, arguments = _parse_tool_call(tc)
                        tool_name = str(name or "")
                        _dbg(f"tool_call name={tool_name} id={call_id!s} args={_shorten_text(arguments, 400)}")

                        # 自动将字符串 command 转为数组
                        if isinstance(arguments, dict):
                            arguments = _coerce_command_to_list(arguments)

                        ok_args, arg_detail = _validate_tool_arguments(tool_name, arguments)
                        if not ok_args:
                            result = {
                                "error": "invalid_tool_arguments",
                                "tool": tool_name,
                                "detail": arg_detail,
                                "got": arguments,
                            }
                            _dbg(f"tool_result name={tool_name} result={_shorten_text(result, 700)}")
                            messages.append(
                                ToolPromptMessage(
                                    tool_call_id=str(call_id or ""),
                                    name=tool_name,
                                    content=json.dumps(result, ensure_ascii=False),
                                )
                            )
                            messages.append(UserPromptMessage(content=_tool_call_retry_prompt(tool_name, arg_detail)))
                            continue

                        if tool_name in {"list_skill_files", "read_skill_file", "run_skill_command"}:
                            skill_name = str(arguments.get("skill_name") or "").strip()
                            if skill_name and not runtime.has_skill_metadata(skill_name):
                                result = {
                                    "error": "skill_md_required",
                                    "skill_name": skill_name,
                                    "detail": "必须先调用 get_skill_metadata(skill_name) 读取 SKILL.md（说明书）后，才能继续调用该工具。",
                                }
                                _dbg(f"tool_result name={tool_name} result={_shorten_text(result, 700)}")
                                messages.append(
                                    ToolPromptMessage(
                                        tool_call_id=str(call_id or ""),
                                        name=tool_name,
                                        content=json.dumps(result, ensure_ascii=False),
                                    )
                                )
                                messages.append(
                                    UserPromptMessage(
                                        content=(
                                            f"你刚才尝试调用 `{tool_name}` 但尚未读取技能《{skill_name}》的 SKILL.md。"
                                            f"请先调用 get_skill_metadata({skill_name!r})，再重试该工具调用。"
                                        )
                                    )
                                )
                                continue

                        # 构建工具操作描述（用于详细模式展示，非详细模式不使用）
                        _skill_name_arg = str(arguments.get("skill_name") or "")
                        _rel_path_arg = str(arguments.get("relative_path") or "")
                        _tp_detail = (
                            _skill_name_arg
                            if tool_name in (
                                "get_skill_metadata", "list_skill_files",
                                "install_skill", "uninstall_skill", "update_skill",
                            )
                            else (_rel_path_arg if tool_name in ("write_temp_file", "read_temp_file", "read_skill_file")
                            else (str(arguments.get("temp_relative_path") or "") if tool_name == "export_temp_file"
                            else ""))
                        )
                        yield from emit_tool_progress(tool_name, _tp_detail)

                        if tool_name == "get_skill_metadata":
                            result = runtime.get_skill_metadata(str(arguments.get("skill_name") or ""))
                        elif tool_name == "list_skill_files":
                            result = runtime.list_skill_files(
                                str(arguments.get("skill_name") or ""),
                                int(arguments.get("max_depth") or 2),
                            )
                        elif tool_name == "read_skill_file":
                            result = runtime.read_skill_file(
                                str(arguments.get("skill_name") or ""),
                                str(arguments.get("relative_path") or ""),
                                int(arguments.get("max_chars") or 12000),
                            )
                        elif tool_name == "run_skill_command":
                            result = runtime.run_skill_command(
                                skill_name=str(arguments.get("skill_name") or ""),
                                command=arguments.get("command") if isinstance(arguments.get("command"), list) else [],
                                cwd_relative=(
                                    str(arguments.get("cwd_relative")) if arguments.get("cwd_relative") else None
                                ),
                                auto_install=bool(arguments.get("auto_install") or False),
                            )
                            if (
                                isinstance(result, dict)
                                and result.get("returncode") is not None
                                and int(result.get("returncode") or 0) != 0
                            ):
                                stderr = str(result.get("stderr") or "").strip()
                                if stderr and verbose:
                                    yield self.create_text_message(
                                        "❌命令执行失败（stderr）：\n" + _shorten_text(redact_user_visible_text(stderr), 1200) + "\n"
                                    )
                            if isinstance(result, dict) and result.get("error") == "no_executable_found":
                                skill = str(result.get("skill") or arguments.get("skill_name") or "")
                                module = str(result.get("module") or "")
                                # 详细模式展示技术细节，非详细模式给出简洁提示
                                if verbose:
                                    forced_text = (
                                    f"当前技能“{skill}”的说明文档要求生成文件，但技能包内未找到可执行入口（例如脚本或 Python 模块）。\n"
                                    f"本次尝试的入口为 python -m {module}，但在技能目录中不存在，因此无法继续生成目标文件。\n\n"
                                    "我已先按技能说明生成了可交付的中间产物（例如设计哲学 .md）。\n"
                                    "你是否允许我在 temp 目录中自行创建可执行脚本，并在需要时安装依赖后，再尝试生成最终文件？"
                                    )
                                else:
                                    forced_text = (
                                        '技能"' + skill + '"需要可执行脚本来完成生成任务，但当前环境中暂无可用入口。\n\n'
                                        "我先生成了可交付的中间产物。是否允许我创建必要的脚本后继续完成？"
                                    )
                                _storage_set_json(
                                    storage,
                                    resume_key,
                                    {
                                        "pending": True,
                                        "session_dir": session_dir,
                                        "original_query": query,
                                        "reason": "no_executable_found",
                                        "skill": skill,
                                        "module": module,
                                        "created_at": int(time.time()),
                                    },
                                )
                                resume_saved = True
                                _dbg(
                                    "resume_state_saved "
                                    + _shorten_text(
                                        {"session_dir": session_dir, "skill": skill, "module": module, "pending": True},
                                        300,
                                    )
                                )
                        elif tool_name == "get_session_context":
                            result = runtime.get_session_context()
                        elif tool_name == "write_temp_file":
                            result = runtime.write_temp_file(
                                str(arguments.get("relative_path") or ""),
                                str(arguments.get("content") or ""),
                            )
                        elif tool_name == "read_temp_file":
                            result = runtime.read_temp_file(
                                str(arguments.get("relative_path") or ""),
                                int(arguments.get("max_chars") or 12000),
                            )
                        elif tool_name == "list_temp_files":
                            result = runtime.list_temp_files(int(arguments.get("max_depth") or 4))
                        elif tool_name == "run_temp_command":
                            result = runtime.run_temp_command(
                                command=arguments.get("command") if isinstance(arguments.get("command"), list) else [],
                                cwd_relative=(
                                    str(arguments.get("cwd_relative")) if arguments.get("cwd_relative") else None
                                ),
                                auto_install=bool(arguments.get("auto_install") or False),
                            )
                            if (
                                isinstance(result, dict)
                                and result.get("returncode") is not None
                                and int(result.get("returncode") or 0) != 0
                            ):
                                stderr = str(result.get("stderr") or "").strip()
                                if stderr and verbose:
                                    yield self.create_text_message(
                                        "❌命令执行失败（stderr）：\n" + _shorten_text(redact_user_visible_text(stderr), 1200) + "\n"
                                    )
                        elif tool_name == "export_temp_file":
                            temp_rel = str(arguments.get("temp_relative_path") or "")
                            workspace_rel = str(arguments.get("workspace_relative_path") or "")
                            result = runtime.export_temp_file(
                                temp_relative_path=temp_rel,
                                workspace_relative_path=workspace_rel,
                                overwrite=bool(arguments.get("overwrite") or False),
                            )
                            out_name = os.path.basename(workspace_rel) if workspace_rel else ""
                            if (
                                isinstance(result, dict)
                                and not result.get("error")
                                and temp_rel
                                and out_name
                            ):
                                final_file_meta[temp_rel] = {
                                    **(final_file_meta.get(temp_rel) or {}),
                                    "filename": out_name,
                                    "mime_type": _guess_mime_type(out_name),
                                }
                        # 技能管理工具分发
                        elif tool_name == "install_skill":
                            result = runtime.install_skill(
                                source_path=str(arguments.get("source_path") or ""),
                                skill_name=str(arguments.get("skill_name") or ""),
                            )
                        elif tool_name == "list_installed_skills":
                            result = runtime.list_installed_skills()
                        elif tool_name == "uninstall_skill":
                            result = runtime.uninstall_skill(
                                skill_name=str(arguments.get("skill_name") or ""),
                            )
                        elif tool_name == "update_skill":
                            result = runtime.update_skill(
                                skill_name=str(arguments.get("skill_name") or ""),
                                source_path=str(arguments.get("source_path") or ""),
                            )
                        else:
                            result = {"error": f"unknown tool: {tool_name}"}

                        _dbg(f"tool_result name={tool_name} result={_shorten_text(result, 700)}")
                        yield from emit_tool_result(tool_name, result)
                        messages.append(
                            ToolPromptMessage(
                                tool_call_id=str(call_id or ""),
                                name=tool_name,
                                content=json.dumps(result, ensure_ascii=False),
                            )
                        )
                    if forced_text:
                        final_text = forced_text
                        break
                    if step_idx >= max_steps - 1:
                        try:
                            has_files = any(
                                e.get("type") == "file"
                                for e in _list_dir(session_dir, max_depth=2)
                                if isinstance(e, dict)
                            )
                        except Exception:
                            has_files = False
                        if final_file_meta or has_files:
                            final_text = "已生成文件。"
                            break
                    continue

                json_text = _extract_first_json_object(res_text)
                action: dict[str, Any] | None = None
                if json_text:
                    try:
                        action = json.loads(json_text)
                    except Exception:
                        action = None
                _dbg(f"json_protocol detected={bool(action)} snippet={_shorten_text(json_text or '', 200)}")

                # 检测 TOOL_RESULT 回声：LLM 把上轮的 TOOL_RESULT 当作自己的输出
                # 格式：{"name":"...","result":{...}} 无 type 字段，或文本以 TOOL_RESULT 开头
                is_tool_result_echo = False
                if action and "name" in action and "result" in action and "type" not in action:
                    is_tool_result_echo = True
                elif res_text and res_text.lstrip().startswith("TOOL_RESULT"):
                    is_tool_result_echo = True

                if is_tool_result_echo and tool_result_echo_count < 2:
                    tool_result_echo_count += 1
                    _dbg(f"tool_result_echo detected (count={tool_result_echo_count}), prompting final answer")
                    messages.append(
                        UserPromptMessage(
                            content="你刚才输出了工具执行结果，但这不是给用户的回答。请直接用自然语言总结数据并给出最终回答，不要重复原始数据。"
                        )
                    )
                    continue
                # 超过重试次数，将回声内容当作最终文本（避免无限循环）
                if is_tool_result_echo:
                    _dbg(f"tool_result_echo max retries reached, treating as final text")

                # 检测不完整的 TOOL_RESULT 输出（如 "TOOL"、"TOOL_R" 等部分前缀但无后续 JSON）
                if res_text and res_text.lstrip().startswith(_TOOL_RESULT_PREFIXES) and tool_result_echo_count < 2:
                    tool_result_echo_count += 1
                    _dbg(f"incomplete_tool_output detected: {_shorten_text(res_text, 100)}, prompting continuation")
                    messages.append(
                        UserPromptMessage(
                            content="你刚才的输出不完整。请继续完成任务：如果需要调用工具请输出完整 JSON，否则请直接输出最终回答。"
                        )
                    )
                    continue

                if not res_text and not action and not nontext:
                    empty_responses += 1
                    _dbg(f"empty_response_count={empty_responses}")
                    if empty_responses < 3:
                        messages.append(
                            UserPromptMessage(
                                content='你刚才没有输出任何内容。请继续完成任务：如果支持函数调用请调用工具；否则请输出 JSON：{"type":"final","content":"..."}'
                            )
                        )
                        continue
                    final_text = "模型连续返回空响应，未生成任何结果。"
                    break

                if not action or action.get("type") == "final":
                    if action and action.get("type") == "final":
                        final_text = str(action.get("content") or "")
                        _dbg(f"final_json content_len={len(final_text)}")
                    else:
                        final_text = res_text
                        _dbg(f"final_text content_len={len(final_text)}")
                        if streamed_any and final_text:
                            final_text_already_streamed = True
                    break

                if action.get("type") != "tool":
                    final_text = res_text
                    _dbg(f"final_non_tool type={action.get('type')!s} content_len={len(final_text)}")
                    break

                name = str(action.get("name") or "")
                arguments = action.get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}

                # 自动将字符串 command 转为数组
                arguments = _coerce_command_to_list(arguments)

                ok_args, arg_detail = _validate_tool_arguments(name, arguments)
                if not ok_args:
                    messages.append(UserPromptMessage(content=_tool_call_retry_prompt(name, arg_detail)))
                    result = {
                        "error": "invalid_tool_arguments",
                        "tool": name,
                        "detail": arg_detail,
                        "got": arguments,
                    }
                    _dbg(f"json_tool_result name={name} result={_shorten_text(result, 700)}")
                    messages.append(
                        AssistantPromptMessage(
                            content="TOOL_RESULT\n" + json.dumps({"name": name, "result": result}, ensure_ascii=False)
                        )
                    )
                    continue

                if name in {"list_skill_files", "read_skill_file", "run_skill_command"}:
                    skill_name = str(arguments.get("skill_name") or "").strip()
                    if skill_name and not runtime.has_skill_metadata(skill_name):
                        messages.append(
                            UserPromptMessage(
                                content=(
                                    f"你刚才尝试调用 `{name}` 但尚未读取技能《{skill_name}》的 SKILL.md。"
                                    f"请先调用 get_skill_metadata({skill_name!r})，再重试该工具调用。"
                                )
                            )
                        )
                        result = {
                            "error": "skill_md_required",
                            "skill_name": skill_name,
                            "detail": "必须先调用 get_skill_metadata(skill_name) 读取 SKILL.md（说明书）后，才能继续调用该工具。",
                        }
                        _dbg(f"json_tool_result name={name} result={_shorten_text(result, 700)}")
                        messages.append(
                            AssistantPromptMessage(
                                content="TOOL_RESULT\n" + json.dumps({"name": name, "result": result}, ensure_ascii=False)
                            )
                        )
                        continue

                _dbg(f"json_tool name={name} args={_shorten_text(arguments, 400)}")
                messages.append(AssistantPromptMessage(content=json.dumps(action, ensure_ascii=False)))

                # JSON 协议路径：统一使用 emit_tool_progress 输出进度
                _j_skill = str(arguments.get("skill_name") or "")
                _j_rel = str(arguments.get("relative_path") or "")
                _j_detail = (
                    _j_skill
                    if name in (
                        "get_skill_metadata", "list_skill_files",
                        "install_skill", "uninstall_skill", "update_skill",
                    )
                    else (_j_rel if name in ("write_temp_file", "read_temp_file", "read_skill_file")
                    else (str(arguments.get("temp_relative_path") or "") if name == "export_temp_file"
                    else ""))
                )
                yield from emit_tool_progress(name, _j_detail)

                if name == "get_skill_metadata":
                    result = runtime.get_skill_metadata(str(arguments.get("skill_name") or ""))
                elif name == "list_skill_files":
                    result = runtime.list_skill_files(
                        str(arguments.get("skill_name") or ""),
                        int(arguments.get("max_depth") or 2),
                    )
                elif name == "read_skill_file":
                    result = runtime.read_skill_file(
                        str(arguments.get("skill_name") or ""),
                        str(arguments.get("relative_path") or ""),
                        int(arguments.get("max_chars") or 12000),
                    )
                elif name == "run_skill_command":
                    result = runtime.run_skill_command(
                        skill_name=str(arguments.get("skill_name") or ""),
                        command=arguments.get("command") if isinstance(arguments.get("command"), list) else [],
                        cwd_relative=(str(arguments.get("cwd_relative")) if arguments.get("cwd_relative") else None),
                        auto_install=bool(arguments.get("auto_install") or False),
                    )
                elif name == "get_session_context":
                    result = runtime.get_session_context()
                elif name == "write_temp_file":
                    result = runtime.write_temp_file(
                        str(arguments.get("relative_path") or ""),
                        str(arguments.get("content") or ""),
                    )
                elif name == "read_temp_file":
                    result = runtime.read_temp_file(
                        str(arguments.get("relative_path") or ""),
                        int(arguments.get("max_chars") or 12000),
                    )
                elif name == "list_temp_files":
                    result = runtime.list_temp_files(int(arguments.get("max_depth") or 4))
                elif name == "run_temp_command":
                    result = runtime.run_temp_command(
                        command=arguments.get("command") if isinstance(arguments.get("command"), list) else [],
                        cwd_relative=(str(arguments.get("cwd_relative")) if arguments.get("cwd_relative") else None),
                        auto_install=bool(arguments.get("auto_install") or False),
                    )
                elif name == "export_temp_file":
                    temp_rel = str(arguments.get("temp_relative_path") or "")
                    workspace_rel = str(arguments.get("workspace_relative_path") or "")
                    result = runtime.export_temp_file(
                        temp_relative_path=temp_rel,
                        workspace_relative_path=workspace_rel,
                        overwrite=bool(arguments.get("overwrite") or False),
                    )
                    out_name = os.path.basename(workspace_rel) if workspace_rel else ""
                    if (
                        isinstance(result, dict)
                        and not result.get("error")
                        and temp_rel
                        and out_name
                    ):
                        final_file_meta[temp_rel] = {
                            **(final_file_meta.get(temp_rel) or {}),
                            "filename": out_name,
                            "mime_type": _guess_mime_type(out_name),
                        }
                # 技能管理工具分发（JSON 协议）
                elif name == "install_skill":
                    result = runtime.install_skill(
                        source_path=str(arguments.get("source_path") or ""),
                        skill_name=str(arguments.get("skill_name") or ""),
                    )
                elif name == "list_installed_skills":
                    result = runtime.list_installed_skills()
                elif name == "uninstall_skill":
                    result = runtime.uninstall_skill(
                        skill_name=str(arguments.get("skill_name") or ""),
                    )
                elif name == "update_skill":
                    result = runtime.update_skill(
                        skill_name=str(arguments.get("skill_name") or ""),
                        source_path=str(arguments.get("source_path") or ""),
                    )
                else:
                    result = {"error": f"unknown tool: {name}"}

                _dbg(f"json_tool_result name={name} result={_shorten_text(result, 700)}")
                yield from emit_tool_result(name, result)
                messages.append(
                    AssistantPromptMessage(
                        content="TOOL_RESULT\n" + json.dumps({"name": name, "result": result}, ensure_ascii=False)
                    )
                )
            else:
                try:
                    has_files = any(
                        e.get("type") == "file" for e in _list_dir(session_dir, max_depth=2) if isinstance(e, dict)
                    )
                except Exception:
                    has_files = False
                if final_file_meta or has_files:
                    final_text = "已生成文件。"
                else:
                    final_text = f"❌超过最大执行轮数 max_steps={max_steps}，仍未得到最终结果"
        finally:
            if not resume_saved and not is_resuming and resume_pending:
                _storage_set_json(storage, resume_key, None)
            temp_files_text = ""
            try:
                temp_entries = _list_dir(session_dir, max_depth=10)
                rel_paths = [
                    str(e.get("relative_path"))
                    for e in temp_entries
                    if e.get("type") == "file" and isinstance(e.get("relative_path"), str)
                ]
                if rel_paths:
                    temp_files_text = "\n\n[temp_files]\n" + "\n".join(rel_paths)
                _dbg(f"temp_files_count={len(rel_paths)}")
            except Exception:
                temp_files_text = ""

            files_to_send: list[tuple[str, str, str, str]] = []
            try:
                for rel, meta_override in (final_file_meta or {}).items():
                    if not rel or not isinstance(rel, str):
                        continue
                    rel_norm = rel.replace("\\", "/").lstrip("/")
                    if not rel_norm:
                        continue
                    try:
                        path = _safe_join(session_dir, rel_norm)
                    except Exception:
                        continue
                    if not os.path.isfile(path):
                        continue
                    filename = os.path.basename(rel_norm)
                    out_name = (meta_override.get("filename") if isinstance(meta_override, dict) else None) or filename
                    mime_type = (meta_override.get("mime_type") if isinstance(meta_override, dict) else None) or _guess_mime_type(out_name or filename)
                    files_to_send.append((rel_norm, path, mime_type, out_name))
            except Exception:
                files_to_send = []

            has_any_files = False
            temp_file_entries: list[dict] = []
            try:
                temp_entries = _list_dir(session_dir, max_depth=10)
                temp_file_entries = [e for e in temp_entries if isinstance(e, dict) and e.get("type") == "file"]
                has_any_files = len(temp_file_entries) > 0
            except Exception:
                has_any_files = False

            # 自动兜底：如果有中间文件但未调用 export_temp_file，自动将所有临时文件作为交付文件
            if not files_to_send and has_any_files:
                try:
                    for entry in temp_file_entries:
                        rel_path = str(entry.get("relative_path") or "").replace("\\", "/").lstrip("/")
                        if not rel_path:
                            continue
                        try:
                            abs_path = _safe_join(session_dir, rel_path)
                        except Exception:
                            continue
                        if not os.path.isfile(abs_path):
                            continue
                        filename = os.path.basename(rel_path)
                        mime_type = _guess_mime_type(filename)
                        files_to_send.append((rel_path, abs_path, mime_type, filename))
                    _dbg(f"auto_exported {len(files_to_send)} temp files (export_temp_file was not called)")
                except Exception:
                    files_to_send = []

            assistant_text_for_history = ""
            if final_text and final_text.strip():
                assistant_text_for_history = final_text.strip()
                _append_history_turn(
                    storage,
                    history_key=history_key,
                    user_text=user_input,
                    assistant_text=assistant_text_for_history,
                )
                if not final_text_already_streamed:
                    yield from stream_text_to_user(final_text)
            elif files_to_send:
                assistant_text_for_history = "已生成文件。"
                _append_history_turn(
                    storage,
                    history_key=history_key,
                    user_text=user_input,
                    assistant_text=assistant_text_for_history,
                )
                yield from stream_text_to_user("已生成文件。")
            else:
                assistant_text_for_history = "未生成任何文本或文件输出。"
                _append_history_turn(
                    storage,
                    history_key=history_key,
                    user_text=user_input,
                    assistant_text=assistant_text_for_history,
                )
                yield from stream_text_to_user("未生成任何文本或文件输出。")

            yielded: set[str] = set()
            yielded_fingerprints: set[str] = set()
            for rel, path, mime_type, out_name in files_to_send:
                if rel in yielded:
                    continue
                yielded.add(rel)
                try:
                    with open(path, "rb") as fp:
                        content = fp.read()
                    try:
                        content_fp = hashlib.sha1(content).hexdigest()
                    except Exception:
                        content_fp = str(len(content))
                    fingerprint_key = f"{out_name}|{mime_type}|{content_fp}"
                    if fingerprint_key in yielded_fingerprints:
                        continue
                    yielded_fingerprints.add(fingerprint_key)
                    yield self.create_blob_message(blob=content, meta={"mime_type": mime_type, "filename": out_name})
                except Exception:
                    continue
            _dbg(f"temp_retained session_dir={session_dir}")
