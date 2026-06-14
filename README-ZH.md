## Skill Agent

**作者：** [liux297](https://github.com/liux297) · 297218348@qq.com
**版本：** 0.2.4
**类型：** 工具插件
**许可证：** Apache-2.0
**项目地址：** https://github.com/liux297/skill_agent

### 本版新增功能

在原版基础上，本版本包含以下实质性增强：

- **自定义变量（`custom_variables`）**：支持将 JSON 键值对注入 Agent 上下文，技能可通过 `get_session_context()` 获取。支持 SKILL.md 中的 `${var}` 模板替换，以及子进程命令的环境变量注入。
- **详细模式（`verbose`）**：可在调试级详细输出和面向用户的简洁输出之间切换。
- **自定义系统提示词（`system_prompt`）**：可覆盖或扩展默认的 Agent 行为指令。
- **渐进式披露优化**：当 SKILL.md 已明确指定可执行入口时，Agent 可直接执行，无需冗余的 `list_skill_files` 调用。
- **智能命令转换**：自动将字符串命令转为数组，并清除从 Markdown 代码块复制时误带的反引号。
- **结构化输出格式化**：命令返回的 JSON 结果自动转换为结构化的中文自然语言摘要。
- **增强诊断信息**：改进了 DNS/网络故障和空 stdout 的错误提示，帮助 LLM 自我诊断问题。

### 简介

Skill Agent 是一个基于 "Skill 渐进式披露（Progressive Disclosure）" 设计的通用型工具插件。它把本地 `skills/` 目录当作"工具箱"，让大模型在需要时逐步读取技能说明、再按需读取文件/执行脚本，最终生成文本或文件交付。

### 适用场景

- 你希望接入 Skill，用"说明书（SKILL.md）+ 文件结构 + 脚本"来约束/增强大模型执行能力
- 你希望输出带有进度提示，并把生成的文件作为工具输出返回
- 你希望把技能封装成可复用的目录（Reference、Scripts 等），而不是把所有逻辑写死在提示词里
- 你希望通过 `custom_variables` 向技能注入运行时上下文（用户身份、团队 ID 等）

### 功能特性

- 渐进式披露：先用技能索引判断，再读取 SKILL.md，再按需读文件/执行命令
- 文件交付：Agent 结束时会把本次 temp 会话目录中的文件作为文件输出返回
- 自由执行：Agent 可以执行任意白名单内的命令，包括读取文件、写入文件、执行脚本等
- 可控记忆：Agent 可设定记忆长度，可执行轮次深度等
- 自定义变量：通过 `${var}` 模板和环境变量向技能注入运行时上下文
- 详细模式开关：调试时展示完整细节，面向用户时隐藏技术细节

### 工具参数

本插件共有两个工具：

**"技能管理"**：用于管理技能目录，可查看技能、新增技能、删除技能、下载技能。
![alt text](_assets/image-0.png)

**"agent_skill"**：通用智能体，可用于执行已存入的技能。
![alt text](_assets/image-1.png)

"agent_skill" 工具支持的参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | 是 | - | 你想问的问题或任务 |
| `model` | model-selector | 是 | - | 运行本工具的大模型 |
| `files` | files | 否 | - | 供 Agent 处理的上传文件 |
| `max_steps` | number | 是 | 15 | 单次调用内最大执行轮数 |
| `memory_turns` | number | 是 | 12 | 单次调用内保留的上下文轮数 |
| `history_turns` | number | 是 | 3 | 跨回合注入的历史对话轮数 |
| `system_prompt` | string | 否 | - | 自定义系统提示词 |
| `custom_variables` | string | 否 | - | JSON 键值对，如 `{"current_user":"Alice"}` |
| `verbose` | boolean | 是 | true | 是否显示详细执行过程 |

`custom_variables` 参数接受 JSON 格式的键值对，会被注入到 Agent 上下文中。技能可通过 `get_session_context()` 获取这些变量，方便在技能脚本中使用当前用户、团队等信息。

### 使用方式（在 Dify 中）

**第一步**：在市场中安装此插件（或上传 `.difypkg` 文件）

**第二步**：自托管用户在 Dify 的 `.env` 中将 `Files_url` 设置为你的 Dify 地址，否则 Dify 获取不到上传的文件

**第三步**：编排工作流，如下图
![alt text](_assets/image-2.png)

**第四步**：管理技能（以 zip 压缩包形式上传技能包）
![alt text](_assets/image-3.png)

**第五步**：与 Skill_Agent 交互
![alt text](_assets/image-4.png)
![alt text](_assets/image-5.png)

### Skill 标准规范

- 每个 skill 必须包含 `SKILL.md`（支持 YAML Frontmatter：`name`、`description`）
- `SKILL.md` 里可以定义触发条件、流程、需要读取的参考文件、需要执行的脚本命令、交付物规范等
- 技能文档中可以使用 `${variable_name}` 占位符，其值来自 `custom_variables` 参数

### 更新历史

**v0.2.4（当前版本）：**
1. `custom_variables` 支持 JSON 键值对注入，含模板替换和环境变量传递
2. `verbose` 模式开关，可在调试级详细输出和面向用户的简洁输出间切换
3. `system_prompt` 参数，可覆盖或扩展默认 Agent 行为指令
4. 优化渐进式披露规则：SKILL.md 已明确可执行入口时，跳过冗余的文件列表操作
5. 字符串命令自动转数组，并清除误带的反引号
6. JSON 结果自动转结构化自然语言摘要
7. 增强 DNS/网络故障和空 stdout 的诊断信息

**历史版本：** 包含流式输出、跨轮次对话、文件记忆、文件上传与解析、依赖安装、技能管理，以及渐进式披露核心架构。

### 常见问题

**1. 安装不上**
有网络的情况下安装不上，可切换一下 Dify 的 pip 源以更好地下载依赖。内网环境下需要通过离线包安装（联系作者）。

**2. 文件传输问题**
上传/下载文件失败（URL 不对、下载超时等），请检查 Dify 的 `.env` 文件是否设置了正确的 `Files_url`，且与 Dify 地址一致。

**3. skill_agent 没有输出**
请确保你的大模型和供应商插件支持 function call 功能。

**4. skill 调用相关**
skill 越完整，Agent 调用越顺畅。保障你的 skill 相关资料、脚本没有缺失。如果是 Node.js 脚本 skill，请先在 Dify 的 `plugin_daemon` 容器中安装 Node.js 环境。

**5. 如何使用 custom_variables**
在 `custom_variables` 字段传入类似 `{"current_user":"Alice","team_id":"T123"}` 的 JSON 字符串。在你的 SKILL.md 或脚本中，可通过 `${current_user}` 引用变量，或通过环境变量（自动转为大写：`$CURRENT_USER`）访问。

### 作者与联系

- **作者：** [liux297](https://github.com/liux297)
- **邮箱：** 297218348@qq.com
- **项目地址：** https://github.com/liux297/skill_agent

### 许可证

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
