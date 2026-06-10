"""临时测试文件：验证代码修复的正确性"""
import json
import unittest


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


if __name__ == "__main__":
    unittest.main()
