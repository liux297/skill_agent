# Skill Agent 变量注入说明（Skill 开发规范）

> 适用版本：skill_agent 0.2.40
> 用途：指导 Skill 开发者按照本插件的变量注入机制编写 SKILL.md 与脚本。

## 一、变量从哪来

工作流中 Skill Agent 节点的 `custom_variables` 参数（`tools/skill_agent.yaml` L182-196），JSON 字符串格式：

```json
{"current_user": "张三", "team_id": "T001", "iv-user": "u_123"}
```

解析规则（`tools/skill_agent.py` L205-209）：
- JSON 解析失败 → **静默变为空**（不报错，Skill 拿不到任何变量）
- 值为 `null` 的键会被丢弃
- 所有键值统一转为**字符串**

## 二、变量注入到 Skill 的 4 条通道

### 通道 1：系统提示词告知 Agent

变量会以 `[自定义变量]` 段落写入 Agent 系统提示词（`tools/skill_agent.py` L411-415），Agent 天然知道有哪些变量可用。

### 通道 2：文本模板替换 `${xxx}`（写 SKILL.md 时用）

实现见 `utils/skill_agent_runtime.py` L278-287，正则为 `\$\{(\w+)\}`：

- **替换范围**：SKILL.md 的 frontmatter 描述、SKILL.md 正文、以及通过 `read_skill_file` 读到的**任何技能文件内容**
- **重要限制**：占位符只支持字母/数字/下划线。**含 `-` 的键（如 `iv-user`）无法用 `${iv-user}` 引用**——正则不匹配，会原样保留。建议变量名统一用下划线（`iv_user`）
- 未匹配到变量的占位符**原样保留**，不会报错

在 SKILL.md 中这样写：

```markdown
---
name: meeting-booking
description: 为 ${current_user} 预定会议室
version: 1.0.0
---

## 使用说明
当前操作人：${current_user}（无需再向用户询问身份）
团队编号：${team_id}
```

### 通道 3：会话上下文 `get_session_context()`

Agent 可调用该工具，返回结构见 `utils/skill_agent_runtime.py` L407-416：

```json
{
  "skills_root": "...",
  "shared_skills_root": "...",
  "skill_space": "...",
  "enabled_skills": [],
  "expected_skill_version": "",
  "session_dir": "...",
  "custom_variables": {"current_user": "张三", "team_id": "T001"}
}
```

**任何键名（含 `-`）都能通过此通道拿到**。可在 SKILL.md 中提示 Agent："执行前先调用 `get_session_context()` 获取 `custom_variables` 中的 xxx 作为命令参数"。

### 通道 4：子进程环境变量（脚本里用）

实现见 `utils/skill_agent_runtime.py` L289-296，命名转换规则：**键名转大写，`-` 替换为 `_`**：

| custom_variables 键 | 脚本中的环境变量 |
|---|---|
| `current_user` | `CURRENT_USER` |
| `team_id` | `TEAM_ID` |
| `iv-user` | `IV_USER` |

`run_skill_command` / `run_temp_command` 执行的所有脚本中可直接读取：

```python
import os
user = os.environ.get("CURRENT_USER", "")
team = os.environ.get("TEAM_ID", "")
```

## 三、SKILL.md 格式要求

Frontmatter 为简单 `key: value`（`utils/tools.py` L113-128），识别字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 建议填 | 缺省用文件夹名 |
| `description` | 建议填 | 供 Agent 渐进式披露匹配，**支持 `${var}` 替换** |
| `version` | 可选 | 语义化版本如 `1.0.0`；也可在正文写 `当前版本: 1.0.0`（版本解析正则见 `utils/skill_agent_runtime.py` L36-38） |

## 四、路径规则（Skill 内引用文件时）

- `run_skill_command` 的工作目录：`skills_root/<skill_name>/`（技能包自身目录）
- 用户上传文件：`session_dir/uploads/<filename>`
- 中间产物/交付文件：`session_dir/` 下
- **引用 uploads 或中间文件时，必须使用 `read_temp_file` 返回的绝对路径（`result.path`）传给命令**，禁止 `../uploads` 这类相对路径猜测
- 最终交付文件必须用 `export_temp_file` 标记

## 五、完整 Skill 编写示例

```
skills/my-skill/
├── SKILL.md
└── run.py
```

**SKILL.md**：

```markdown
---
name: my-skill
description: 使用 ${current_user} 的身份执行业务查询
version: 1.0.0
---

## 执行入口
直接执行：python run.py
无需额外参数，脚本从环境变量 CURRENT_USER、TEAM_ID 读取身份信息。

## 规则
- 身份已由调用方注入，禁止再向用户确认
- 输出为 JSON 时由 Agent 转成中文摘要
```

**run.py**：

```python
import os, json

# 变量通过环境变量注入（键名大写、- 转 _）
user = os.environ.get("CURRENT_USER", "")
team = os.environ.get("TEAM_ID", "")

print(json.dumps({"user": user, "team": team}, ensure_ascii=False))
```

## 六、避坑清单

1. **变量名避免用 `-`**：模板通道 `${...}` 只认 `\w`，含 `-` 的键只能走环境变量或 `get_session_context`
2. **custom_variables JSON 写错不报错**：解析失败静默为空，Skill 拿到的全是默认值，排查时先确认 JSON 格式
3. **占位符未替换会原样输出**：说明变量键名拼写与配置不一致
4. **值全是字符串**：数字/布尔传入后均为字符串，脚本中自行转换
5. **别在 SKILL.md 里写 curl 命令文本**：系统会拒绝，所有命令必须通过 `run_skill_command` 执行（`tools/skill_agent.py` L438）

## 附注：与 GUIDE.md 的差异

GUIDE.md Recipe 9 示例写了 `${iv-user}`，但代码正则 `\w+` 不匹配含 `-` 的键，实际该写法不会替换。开发时统一用下划线命名规避。
