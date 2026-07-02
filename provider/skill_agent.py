from typing import Any

from dify_plugin import ToolProvider


class SkillProvider(ToolProvider):

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # 当前插件无需凭证验证（skills_root 通过参数传入）
        pass

