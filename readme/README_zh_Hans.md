## Skill Agent

**作者：** [liux297](https://github.com/liux297) · 297218348@qq.com
**版本：** 0.2.31
**类型：** 工具插件
**许可证：** Apache-2.0
**项目地址：** https://github.com/liux297/skill_agent

### v0.2.31 新增功能

Skill Agent 是基于 Skill 渐进式披露模式构建的通用型 Agent 插件，参考/借鉴 OpenClaw 与 Hermes 的 Agent 架构设计。v0.2.31 在原有能力上增加工作流级 Skill Space、技能范围限制、版本校验、公共只读技能与按名称管理。

- **双协议智能切换**：自动检测模型 FC 能力，兼容 Function Calling 和 JSON 协议两种模式
- **渐进式披露优化**：先用技能索引判断，再读取 SKILL.md，再按需读文件/执行命令，避免冗余操作
- **上下文智能压缩**：基于 token 估算的上下文管理与自动恢复机制
- **命令白名单沙箱**：安全的脚本执行控制，防止危险命令执行
- **文件交付机制**：Agent 结束时会把 temp 会话目录中的文件作为文件输出返回
- **流式对话输出**：支持实时自然语言流式输出，隐藏内部协议消息
- **自定义变量注入**：支持 `custom_variables` JSON 键值对注入，含 `${var}` 模板替换和环境变量传递
- **详细模式开关**：调试级详细输出与面向用户的简洁输出自由切换
- **自定义系统提示词**：可覆盖或扩展默认 Agent 行为指令

### 简介

Skill Agent 是一个基于 "Skill 渐进式披露（Progressive Disclosure）" 设计的通用型工具插件，参考/借鉴 OpenClaw 与 Hermes 的 Agent 架构设计。每个工作流可以选择独立的 Skill Space 作为“工具箱”，让大模型在需要时逐步读取技能说明、再按需读取文件/执行脚本，最终生成文本或文件交付。

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
- 工作流级 Skill Space：不同工作流可选择独立技能库，也可按需加载公共只读技能
- 稳定名称管理：按技能目录名称删除和下载，不再依赖会变化的序号

### 工具参数

本插件共有两个工具：

**"技能管理"**：管理指定 Skill Space，可查看、新增技能，并按稳定名称删除或下载技能。
![alt text](../_assets/image-0.png)

**"agent_skill"**：通用智能体，可用于执行已存入的技能。
![alt text](../_assets/image-1.png)

"agent_skill" 工具支持的参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | 是 | - | 你想问的问题或任务 |
| `model` | model-selector | 是 | - | 运行本工具的大模型 |
| `files` | files | 否 | - | 供 Agent 处理的上传文件 |
| `skill_space` | string | 是 | `default` | 当前工作流选择的独立技能库名称 |
| `enabled_skills` | string | 否 | - | 允许使用的技能目录名，逗号分隔；留空表示全部 |
| `skill_version` | string | 否 | - | 单个启用技能的固定版本，版本不匹配时停止执行 |
| `include_shared_skills` | boolean | 是 | false | 是否加载 `shared` 公共只读空间 |
| `max_steps` | number | 是 | 15 | 单次调用内最大执行轮数 |
| `memory_turns` | number | 是 | 12 | 单次调用内保留的上下文轮数 |
| `history_turns` | number | 是 | 3 | 跨回合注入的历史对话轮数 |
| `system_prompt` | string | 否 | - | 自定义系统提示词 |
| `custom_variables` | string | 否 | - | JSON 键值对，如 `{"current_user":"Alice"}` |
| `verbose` | boolean | 是 | false | 调试模式：显示命令、路径、参数与执行输出 |

`custom_variables` 参数接受 JSON 格式的键值对，会被注入到 Agent 上下文中。技能可通过 `get_session_context()` 获取这些变量，方便在技能脚本中使用当前用户、团队等信息。

### 使用方式（在 Dify 中）

**第一步**：在市场中安装此插件（或上传 `.difypkg` 文件）

**第二步**：自托管用户在 Dify 的 `.env` 中将 `Files_url` 设置为你的 Dify 地址，否则 Dify 获取不到上传的文件

**第三步**：编排工作流，如下图
![alt text](../_assets/image-2.png)

**第四步**：管理技能（以 zip 压缩包形式上传技能包）
![alt text](../_assets/image-3.png)

技能管理与 Skill Agent 节点应配置相同的 `skill_space`。管理命令使用稳定名称：`查看技能`、`新增技能`、`删除技能 <名称>`、`下载技能 <名称>`。

**第五步**：与 Skill_Agent 交互
![alt text](../_assets/image-4.png)
![alt text](../_assets/image-5.png)

### Skill 标准规范

- 每个 skill 必须包含 `SKILL.md`（支持 YAML Frontmatter：`name`、`description`）
- `SKILL.md` 里可以定义触发条件、流程、需要读取的参考文件、需要执行的脚本命令、交付物规范等
- 技能文档中可以使用 `${variable_name}` 占位符，其值来自 `custom_variables` 参数

### 更新历史

**v0.2.31（当前版本）：**
1. 工作流通过 `skill_space` 选择互相隔离的技能库
2. 支持 `enabled_skills` 技能白名单和单技能版本校验
3. 可选择加载 `shared` 公共只读技能，同名时私有空间优先
4. 技能管理按稳定名称删除、下载，不再依赖序号
5. 对话存储键和临时目录按 Skill Space 隔离

**v0.2.9：**
1. 双协议智能切换：自动检测模型 FC 能力，兼容 Function Calling 和 JSON 协议两种模式
2. 渐进式披露优化：避免冗余的文件列表操作，提高执行效率
3. 上下文智能压缩：基于 token 估算的上下文管理与自动恢复机制
4. 命令白名单沙箱：安全的脚本执行控制
5. 文件交付机制：Agent 结束时返回 temp 会话目录中的文件
6. 流式对话输出：支持实时自然语言流式输出
7. `custom_variables` 支持 JSON 键值对注入，含模板替换和环境变量传递
8. `verbose` 模式开关，可在调试级详细输出和面向用户的简洁输出间切换
9. `system_prompt` 参数，可覆盖或扩展默认 Agent 行为指令

**历史版本：** 包含 JSON 智能压缩、模型能力自适应检测、统一工具执行管线、Token 感知上下文压缩、流式输出、跨轮次对话、文件记忆、文件上传与解析、依赖安装、技能管理，以及渐进式披露核心架构。

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
