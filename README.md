## Skill Agent

**Author / 作者：** [liux297](https://github.com/liux297)
**Version / 版本：** 0.1.0 | **Type / 类型：** Tool (Plugin) | **License / 许可证：** Apache-2.0

---

### 简介 / Introduction

Skill Agent 是一个基于 "Skill 渐进式披露（Progressive Disclosure）" 设计的通用型工具插件。它把本地 `skills/` 目录当作"工具箱"，让大模型在需要时逐步读取技能说明、再按需读取文件/执行脚本，最终生成文本或文件交付。

Skill Agent is a general-purpose tool plugin based on "Skill Progressive Disclosure". It treats the local `skills/` directory as a toolbox, so the model can read the skill manual on demand, then read files / run scripts only when necessary, and finally deliver text or files.

### 致谢 / Acknowledgements

基于 [lfenghx 的 Skill Agent](https://github.com/lfenghx/skill_agent)（Apache-2.0）开发。

Based on [Skill Agent by lfenghx](https://github.com/lfenghx/skill_agent) (Apache-2.0).

---

### 本版新增功能 / What's New

在原版基础上，本版本包含以下实质性增强：

This version includes meaningful enhancements on top of the original:

- **自定义变量（`custom_variables`）/ Custom Variables**：支持将 JSON 键值对注入 Agent 上下文，技能可通过 `get_session_context()` 获取。支持 SKILL.md 中的 `${var}` 模板替换，以及子进程命令的环境变量注入。 / Inject JSON key-value pairs into agent context; skills can access them via `get_session_context()`. Supports `${var}` template replacement in SKILL.md and environment variable injection for subprocess commands.
- **详细模式（`verbose`）/ Verbose Mode**：可在调试级详细输出和面向用户的简洁输出之间切换。 / Toggle between detailed tool execution progress (for debugging) and clean user-facing output (for production).
- **自定义系统提示词（`system_prompt`）/ Custom System Prompt**：可覆盖或扩展默认的 Agent 行为指令。 / Override or extend default agent behavior instructions.
- **渐进式披露优化 / Optimized Progressive Disclosure**：当 SKILL.md 已明确指定可执行入口时，Agent 可直接执行，无需冗余的 `list_skill_files` 调用。 / When SKILL.md already specifies an executable entry point, the agent can execute directly without redundant `list_skill_files` calls.
- **智能命令转换 / Smart Command Coercion**：自动将字符串命令转为数组，并清除从 Markdown 代码块复制时误带的反引号。 / Automatically converts string commands to arrays and strips backticks accidentally copied from Markdown code blocks.
- **结构化输出格式化 / Structured Output Formatting**：命令返回的 JSON 结果自动转换为结构化的自然语言摘要。 / Command results returned as JSON are automatically converted to structured natural-language summaries.
- **增强诊断信息 / Enhanced Diagnostics**：改进了 DNS/网络故障和空 stdout 的错误提示，帮助 LLM 自我诊断问题。 / Improved error messages for DNS/network failures and empty stdout to help the LLM self-diagnose issues.

---

### 适用场景 / Use Cases

- 你希望接入 Skill，用"说明书（SKILL.md）+ 文件结构 + 脚本"来约束/增强大模型执行能力 / You want to integrate Skills and constrain/strengthen the model using "manual (SKILL.md) + file structure + scripts"
- 你希望输出带有进度提示，并把生成的文件作为工具输出返回 / You want progress messages and to return generated files as tool outputs
- 你希望把技能封装成可复用的目录（Reference、Scripts 等），而不是把所有逻辑写死在提示词里 / You want to package capabilities as reusable skill folders instead of hard-coding everything in prompts
- 你希望通过 `custom_variables` 向技能注入运行时上下文（用户身份、团队 ID 等） / You want to inject runtime context into skills via custom variables

---

### 功能特性 / Features

- 渐进式披露：先用技能索引判断，再读取 SKILL.md，再按需读文件/执行命令 / Progressive disclosure: skill index -> read `SKILL.md` -> read files / run commands as needed
- 文件交付：Agent 结束时会把本次 temp 会话目录中的文件作为文件输出返回 / File delivery: all files in the temp session directory are returned when the agent finishes
- 自由执行：Agent 可以执行任意白名单内的命令 / Free execution: the agent can execute whitelisted commands
- 可控记忆：Agent 可设定记忆长度，可执行轮次深度等 / Controllable memory: configurable memory turns and max step depth
- 自定义变量：通过 `${var}` 模板和环境变量向技能注入运行时上下文 / Custom variables: inject runtime context via `${var}` templates and environment variables
- 详细模式开关：调试时展示完整细节，面向用户时隐藏技术细节 / Verbose mode: switch between debug-level detail and clean user-facing output

---

### 工具参数 / Tool Parameters

本插件共有两个工具 / This plugin provides two tools：

- **"技能管理 / Skill Manager"**：用于管理技能目录，可查看技能、新增技能、删除技能、下载技能。 / Manages the local skills directory (list/add/delete/download skills).
  ![alt text](_assets/image-0.png)
- **"agent_skill"**：通用智能体，可用于执行已存入的技能。 / A general agent that can execute skills that have been stored.
  ![alt text](_assets/image-1.png)

"agent_skill" 工具支持的参数 / The "agent_skill" tool accepts the following parameters：

| 参数 / Parameter | 类型 / Type | 必填 / Required | 默认值 / Default | 说明 / Description |
|------|------|------|--------|------|
| `query` | string | 是 / Yes | - | 你想问的问题或任务 / Your question or task for the agent |
| `model` | model-selector | 是 / Yes | - | 运行本工具的大模型 / LLM to run this tool |
| `files` | files | 否 / No | - | 供 Agent 处理的上传文件 / File(s) for the agent to process |
| `max_steps` | number | 是 / Yes | 15 | 单次调用内最大执行轮数 / Max reasoning/tool steps per call |
| `memory_turns` | number | 是 / Yes | 12 | 单次调用内保留的上下文轮数 / Recent turns to keep during the run |
| `history_turns` | number | 是 / Yes | 3 | 跨回合注入的历史对话轮数 / Previous runs to inject as transcript |
| `system_prompt` | string | 否 / No | - | 自定义系统提示词 / Custom system prompt to override defaults |
| `custom_variables` | string | 否 / No | - | JSON 键值对，如 `{"current_user":"Alice"}` / JSON key-value pairs |
| `verbose` | boolean | 是 / Yes | true | 是否显示详细执行过程 / Show detailed execution progress |

`custom_variables` 参数接受 JSON 格式的键值对，会被注入到 Agent 上下文中。技能可通过 `get_session_context()` 获取这些变量，方便在技能脚本中使用当前用户、团队等信息。

The `custom_variables` parameter accepts a JSON object of key-value pairs that will be injected into the agent context. Skills can access these variables via the `get_session_context()` action, making it easy to pass user identity, team info, or other runtime context to skills.

---

### 使用方式 / How to Use (in Dify)

**第一步**：在市场中安装此插件（或上传 `.difypkg` 文件） / **Step 1**: Install this plugin from the Marketplace (or upload `.difypkg` file)

**第二步**：自托管用户在 Dify 的 `.env` 中将 `Files_url` 设置为你的 Dify 地址，否则 Dify 获取不到上传的文件 / **Step 2**: For self-hosted deployments, set `Files_url` in Dify's `.env` to your Dify address, otherwise Dify cannot fetch uploaded files

**第三步**：编排工作流，如下图 / **Step 3**: Build your workflow as shown below
![alt text](_assets/image-2.png)

**第四步**：管理技能（以 zip 压缩包形式上传技能包） / **Step 4**: Manage skills (upload skill packages as zip files)
![alt text](_assets/image-3.png)

**第五步**：与 Skill_Agent 交互 / **Step 5**: Chat with Skill Agent
![alt text](_assets/image-4.png)
![alt text](_assets/image-5.png)

---

### Skill 标准规范 / Skill Standard

- 每个 skill 必须包含 `SKILL.md`（支持 YAML Frontmatter：`name`、`description`） / Every skill must include `SKILL.md` (YAML frontmatter supported: `name`, `description`)
- `SKILL.md` 里可以定义触发条件、流程、需要读取的参考文件、需要执行的脚本命令、交付物规范等 / `SKILL.md` can define trigger conditions, workflow, required reference reads, commands to run, and deliverable specs
- 技能文档中可以使用 `${variable_name}` 占位符，其值来自 `custom_variables` 参数 / Skills can use `${variable_name}` placeholders that are replaced by values from `custom_variables`

---

### 更新历史 / Changelog

**v0.1.0（本版本 / this version）：**
1. 新增 `custom_variables` 参数，支持运行时上下文注入 / Add `custom_variables` parameter for runtime context injection
2. 新增 `verbose` 模式开关 / Add `verbose` mode toggle
3. 新增 `system_prompt` 参数 / Add `system_prompt` parameter
4. 优化渐进式披露规则 / Optimize progressive disclosure rule
5. 新增字符串命令自动转数组功能 / Add auto coercion of string commands to arrays
6. 新增 JSON 结果自动转自然语言摘要 / Add structured JSON-to-natural-language formatting
7. 增强 DNS/网络故障诊断信息 / Enhance diagnostics for DNS failures and empty stdout
8. 版本升级至 0.1.0 / Version bump to 0.1.0

**v0.0.3（原作者 lfenghx 版本 / original by lfenghx）：**
1. 支持 Agent 流式输出 / Support agent streaming output
2. 支持 Agent 跨轮次交互式对话 / Support interactive, multi-turn conversations across turns
3. 支持文件记忆 / Support file memory
4. 支持 Node.js 脚本运行的 skill / Support running Node.js scripts as skills
5. 提升 skill_agent 运行稳定性 / Improve skill_agent runtime stability

**v0.0.2：** 支持 Agent 文件上传与解析；支持依赖自行安装 / Support agent file upload and parsing; support automatic dependency installation

**v0.0.1：** 实现技能管理，按渐进式披露方式工作的通用型 Agent / Implement skill management and a general agent that works with progressive disclosure

---

### 常见问题 / FAQ

**1. 安装不上 / Installation issues**
有网络的情况下安装不上，可切换一下 Dify 的 pip 源以更好地下载依赖。内网环境下需要通过离线包安装（联系作者）。 / If installation fails with network access available, try switching Dify's pip mirror. In intranet environments, install via an offline package (contact the author).

**2. 文件传输问题 / File transfer issues**
上传/下载文件失败，请检查 Dify 的 `.env` 文件是否设置了正确的 `Files_url`。 / If uploading/downloading files fails, check whether Dify's `.env` has `Files_url` set correctly.

**3. skill_agent 没有输出 / No output from skill_agent**
属于大模型的问题，请确保你的大模型和供应商插件支持 function call 功能。推荐 DeepSeek-V3.1。 / This is usually due to the model. Make sure your model and provider plugin support function calling. DeepSeek-V3.1 is recommended.

**4. skill 调用相关 / Skill invocation issues**
skill 越完整，Agent 调用越顺畅。保障你的 skill 相关资料、脚本没有缺失。 / The more complete your skill is, the more smoothly the agent can invoke it. Ensure your skill materials and scripts are not missing.

**5. 如何使用 custom_variables / Using custom_variables**
在 `custom_variables` 字段传入类似 `{"current_user":"Alice","team_id":"T123"}` 的 JSON 字符串。在你的 SKILL.md 或脚本中，可通过 `${current_user}` 引用变量，或通过环境变量（自动转为大写：`$CURRENT_USER`）访问。 / Pass a JSON string like `{"current_user":"Alice","team_id":"T123"}`. Reference variables as `${current_user}` or via environment variables (auto uppercased: `$CURRENT_USER`).

---

### 作者与联系 / Author & Contact

- **作者 / Author：** [liux297](https://github.com/liux297)
- **邮箱 / Email：** 297218348@qq.com

### 许可证 / License

Copyright (c) 2026 liux297

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

**原始作品 / Original work：** Copyright (c) 2026 lfenghx — [原始仓库 / original repository](https://github.com/lfenghx/skill_agent)
