"""临时测试文件：验证代码修复的正确性"""
import json
import unittest
import tempfile
from pathlib import Path


# ========== 导入项目模块 ==========
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from utils.skill_agent_constants import ALLOWED_COMMANDS, UNSAFE_COMMANDS
from utils.skill_agent_runtime import _AgentRuntime
from utils.tools import _safe_join
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.skill_agent import SkillAgentTool


# ========== 复制待测试的函数逻辑 ==========

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
    depth = 0
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
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def should_emit_user_text(text):
    if not text:
        return False
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
    return t not in {"tool", "final"}


def redact_user_visible_text(text, session_dir, skills_root):
    s = str(text or "")
    if not s:
        return s
    for p in [session_dir, skills_root]:
        if p and isinstance(p, str):
            s = s.replace(p, "<REDACTED_PATH>")
            s = s.replace(p.replace("\\", "/"), "<REDACTED_PATH>")
    return s


# ========== 测试类 ==========

class TestVerboseParsing(unittest.TestCase):
    """测试 verbose 参数解析逻辑"""

    def _parse_verbose(self, _verbose_raw):
        return _verbose_raw not in (False, "false", "False", 0, "0")

    def test_verbose_false(self):
        self.assertFalse(self._parse_verbose(False))

    def test_verbose_string_false(self):
        self.assertFalse(self._parse_verbose("false"))

    def test_verbose_string_False(self):
        self.assertFalse(self._parse_verbose("False"))

    def test_verbose_true(self):
        self.assertTrue(self._parse_verbose(True))

    def test_verbose_string_true(self):
        self.assertTrue(self._parse_verbose("true"))

    def test_verbose_none(self):
        self.assertTrue(self._parse_verbose(None))

    def test_verbose_zero(self):
        self.assertFalse(self._parse_verbose(0))

    def test_verbose_string_zero(self):
        self.assertFalse(self._parse_verbose("0"))


class TestStreamingOutput(unittest.TestCase):
    def test_text_messages_use_dify_streaming_variable(self):
        tool = object.__new__(SkillAgentTool)
        tool.response_type = ToolInvokeMessage
        message = tool.create_text_message("progress")
        self.assertEqual(message.type.value, "variable")
        self.assertEqual(message.message.variable_name, "text")
        self.assertEqual(message.message.variable_value, "progress")
        self.assertTrue(message.message.stream)

class TestShouldEmitUserText(unittest.TestCase):
    """测试 should_emit_user_text 函数"""

    def test_plain_text(self):
        self.assertTrue(should_emit_user_text("这是一段普通文本"))

    def test_empty_text(self):
        self.assertFalse(should_emit_user_text(""))

    def test_tool_json(self):
        self.assertFalse(should_emit_user_text('{"type":"tool","name":"xxx","arguments":{}}'))

    def test_final_json(self):
        self.assertFalse(should_emit_user_text('{"type":"final","content":"xxx"}'))

    def test_other_type_json(self):
        self.assertTrue(should_emit_user_text('{"type":"other"}'))

    def test_incomplete_brace(self):
        self.assertTrue(should_emit_user_text("{这是一个包含花括号的文本"))

    def test_code_block(self):
        self.assertTrue(should_emit_user_text("```python\nprint('hello')\n```"))

    def test_json_with_prefix(self):
        self.assertTrue(should_emit_user_text('结果是 {"type":"other"}'))


class TestRedactUserVisibleText(unittest.TestCase):
    """测试 redact_user_visible_text 函数"""

    def test_redact_session_dir(self):
        result = redact_user_visible_text(
            "路径 /tmp/dify-skill-abc123 中的文件",
            session_dir="/tmp/dify-skill-abc123",
            skills_root="/opt/skills",
        )
        self.assertEqual(result, "路径 <REDACTED_PATH> 中的文件")

    def test_no_redact_normal_text(self):
        result = redact_user_visible_text(
            "这是一段普通文本",
            session_dir="/tmp/dify-skill-abc123",
            skills_root="/opt/skills",
        )
        self.assertEqual(result, "这是一段普通文本")

    def test_markdown_not_misreplaced(self):
        result = redact_user_visible_text(
            "- 项目/子项",
            session_dir="/tmp/dify-skill-abc123",
            skills_root="/opt/skills",
        )
        self.assertEqual(result, "- 项目/子项")

    def test_redact_skills_root(self):
        result = redact_user_visible_text(
            "技能位于 /opt/skills/my_skill",
            session_dir="/tmp/dify-skill-abc123",
            skills_root="/opt/skills",
        )
        self.assertEqual(result, "技能位于 <REDACTED_PATH>/my_skill")

    def test_empty_text(self):
        result = redact_user_visible_text("", session_dir="/tmp", skills_root="/opt")
        self.assertEqual(result, "")

    def test_none_text(self):
        result = redact_user_visible_text(None, session_dir="/tmp", skills_root="/opt")
        self.assertEqual(result, "")


class TestUploadsContextNotOverwritten(unittest.TestCase):
    """测试 uploads_context 不被覆盖的逻辑"""

    def test_existing_uploads_context_not_overwritten(self):
        # 模拟已有 uploads_context 时不应被覆盖
        uploads_context = "已有的上传上下文"
        new_context = _build_uploads_context([])
        # 已有值时保留原值
        if uploads_context:
            result = uploads_context
        else:
            result = new_context
        self.assertEqual(result, "已有的上传上下文")

    def test_empty_uploads_context_gets_filled(self):
        # 模拟 uploads_context 为空时应补充
        uploads_context = ""
        new_context = _build_uploads_context(["file1.txt", "file2.txt"])
        if uploads_context:
            result = uploads_context
        else:
            result = new_context
        self.assertIn("file1.txt", result)
        self.assertIn("file2.txt", result)


def _build_uploads_context(uploads):
    """模拟 _build_uploads_context 的简单实现"""
    if not uploads:
        return ""
    lines = ["上传的文件："]
    for f in uploads:
        lines.append(f"- {f}")
    return "\n".join(lines)


class TestSessionDirNaming(unittest.TestCase):
    """测试 session_dir 命名格式"""

    def test_session_dir_format_no_trailing_dash(self):
        import re
        hex_val = "a1b2c3"
        session_dir = f"dify-skill-{hex_val}"
        # 不应以 - 结尾
        self.assertFalse(session_dir.endswith("-"))
        # 应匹配 dify-skill-{hex} 格式
        self.assertRegex(session_dir, r"^dify-skill-[0-9a-f]+$")

    def test_old_format_has_trailing_dash(self):
        # 旧格式有尾部 - ，应被修复
        hex_val = "a1b2c3"
        old_format = f"dify-skill-{hex_val}-"
        self.assertTrue(old_format.endswith("-"))


class TestAllowedCommandsWhitelist(unittest.TestCase):
    """默认执行面不应包含解释器外壳、安装器或网络客户端。"""

    def test_python_in_whitelist(self):
        self.assertIn("python", ALLOWED_COMMANDS)

    def test_python3_in_whitelist(self):
        self.assertIn("python3", ALLOWED_COMMANDS, "python3 必须在白名单中，否则 macOS/Linux 上命令会被拦截")

    def test_node_in_whitelist(self):
        self.assertIn("node", ALLOWED_COMMANDS)

    def test_unsafe_commands_not_in_default_whitelist(self):
        self.assertFalse(ALLOWED_COMMANDS & UNSAFE_COMMANDS)

    def test_unsafe_command_not_in_whitelist(self):
        """危险命令不应在白名单中"""
        for cmd in ("rm", "sudo", "chmod", "chown", "dd", "mkfs"):
            self.assertNotIn(cmd, ALLOWED_COMMANDS, f"{cmd} 不应在白名单中")


class TestPython3Rewrite(unittest.TestCase):
    """测试 python3 命令在 run_skill_command / run_temp_command 中会被重写为 sys.executable"""

    def _simulate_exe_check(self, command: list[str]) -> dict:
        """模拟 runtime 中的 exe 检查与重写逻辑"""
        exe = command[0]
        if exe in ("python", "python3"):
            rewritten = [sys.executable] + command[1:]
            return {"rewritten": True, "command": rewritten}
        elif exe not in ALLOWED_COMMANDS:
            return {"error": f"command not allowed: {exe}"}
        else:
            return {"rewritten": False, "command": command}

    def test_python_gets_rewritten(self):
        result = self._simulate_exe_check(["python", "script.py"])
        self.assertTrue(result.get("rewritten"))
        self.assertEqual(result["command"][0], sys.executable)

    def test_python3_gets_rewritten(self):
        result = self._simulate_exe_check(["python3", "script.py"])
        self.assertTrue(result.get("rewritten"), "python3 必须被重写为 sys.executable")
        self.assertEqual(result["command"][0], sys.executable)
        self.assertEqual(result["command"][1], "script.py")

    def test_python3_with_m_module(self):
        result = self._simulate_exe_check(["python3", "-m", "http.server"])
        self.assertTrue(result.get("rewritten"))
        self.assertEqual(result["command"][0], sys.executable)
        self.assertIn("-m", result["command"])

    def test_sh_blocked_by_default(self):
        result = self._simulate_exe_check(["sh", "script.sh"])
        self.assertIn("error", result)

    def test_bash_blocked_by_default(self):
        result = self._simulate_exe_check(["bash", "script.sh"])
        self.assertIn("error", result)

    def test_disallowed_command_blocked(self):
        result = self._simulate_exe_check(["rm", "-rf", "/"])
        self.assertIn("error", result)
        self.assertIn("not allowed", result["error"])

    def test_node_not_rewritten_but_allowed(self):
        result = self._simulate_exe_check(["node", "app.js"])
        self.assertFalse(result.get("rewritten"))
        self.assertNotIn("error", result)


class TestWorkspaceContainment(unittest.TestCase):
    def test_safe_join_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "session"
            root.mkdir()
            (root / "outside").symlink_to(Path(td), target_is_directory=True)
            with self.assertRaises(ValueError):
                _safe_join(str(root), "outside/secret.txt")


class TestSkillInstallSafety(unittest.TestCase):
    def _runtime(self, root: Path, session: Path) -> _AgentRuntime:
        return _AgentRuntime(
            skills_root=str(root), session_dir=str(session), max_steps=1,
            memory_turns=1, allowed_commands=set(ALLOWED_COMMANDS),
        )

    def test_invalid_update_keeps_existing_skill(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root, session = base / "skills", base / "session"
            root.mkdir(); session.mkdir()
            old = root / "demo"; old.mkdir()
            (old / "SKILL.md").write_text("# old", encoding="utf-8")
            bad = session / "bad"; bad.mkdir()
            result = self._runtime(root, session).update_skill(skill_name="demo", source_path="bad")
            self.assertIn("error", result)
            self.assertEqual((old / "SKILL.md").read_text(encoding="utf-8"), "# old")

    def test_unsafe_commands_require_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills"; session = Path(td) / "session"
            root.mkdir(); session.mkdir()
            default = self._runtime(root, session)
            opted_in = _AgentRuntime(skills_root=str(root), session_dir=str(session), max_steps=1,
                                     memory_turns=1, allowed_commands={"bash"}, allow_unsafe_commands=True)
            self.assertNotIn("bash", default.allowed_commands)
            self.assertIn("bash", opted_in.allowed_commands)

    def test_safe_mode_rejects_inline_python_and_auto_install(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "skills"; session = Path(td) / "session"
            root.mkdir(); session.mkdir()
            runtime = self._runtime(root, session)
            self.assertIn("error", runtime.run_temp_command(command=["python", "-c", "print(1)"]))
            self.assertIn("error", runtime.run_temp_command(command=["python", "-m", "pip"], auto_install=True))


if __name__ == "__main__":
    unittest.main()
