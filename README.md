## Skill Agent

**Author:** [liux297](https://github.com/liux297) · 297218348@qq.com
**Version:** 0.2.31
**Type:** Tool Plugin
**License:** Apache-2.0
**Repository:** https://github.com/liux297/skill_agent

### Overview

Skill Agent is a universal Agent plugin built on the "Skill Progressive Disclosure" pattern, inspired by OpenClaw and Hermes agent architecture designs. Each workflow can select an isolated Skill Space as its toolbox, allowing the LLM to progressively read skill instructions, files, and execute scripts on demand, ultimately generating text or file deliverables.

### Key Features

- **Dual-protocol smart switching**: Auto-detects model Function Calling capability, compatible with both FC and JSON protocols
- **Progressive disclosure**: Skill index lookup first, then read SKILL.md, then read files/execute commands as needed
- **Context smart compression**: Token-based context management with auto-recovery mechanism
- **Safer execution defaults**: Shells, package managers, and network clients require an explicit high-risk opt-in; use only with trusted skills
- **File delivery**: Agent returns files from the temp session directory as tool output
- **True streaming output**: Progress and final text use Dify streaming variables for incremental typewriter-style display instead of being returned in one batch
- **Custom variable injection**: Supports `custom_variables` JSON key-value pairs with `${var}` template replacement and environment variable passing
- **Verbose mode toggle**: Debug-level detailed output vs user-facing concise output
- **Custom system prompt**: Override or extend the default Agent behavior instructions
- **Step-by-step progress**: Each tool execution step displays icon, step number, operation description, elapsed time, and result summary
- **Workflow-level Skill Spaces**: Different workflows can select isolated libraries, optional shared read-only skills, an allow-list, and a fail-closed expected version
- **Stable name-based management**: List, delete and download skills by folder name instead of unstable numeric positions

### Use Cases

- You want to use Skills with "SKILL.md + file structure + scripts" to enhance LLM execution capabilities
- You want output with progress indicators and generated files returned as tool output
- You want to package skills as reusable directories (Reference, Scripts, etc.) instead of hardcoding all logic in prompts
- You want to inject runtime context (user identity, team ID, etc.) into skills via `custom_variables`

### Tools

This plugin provides two tools:

**Skill Manager**: Manage one selected Skill Space — view/add skills and delete/download them by stable folder name.

**Skill Agent**: Universal agent for executing installed skills.

### Skill Agent Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Your question or task |
| `model` | model-selector | Yes | - | LLM to run this tool |
| `files` | files | No | - | Uploaded files for the Agent to process |
| `skill_space` | string | Yes | `default` | Isolated skill library selected by this workflow |
| `enabled_skills` | string | No | - | Comma-separated allow-list of skill folder names; empty means all |
| `skill_version` | string | No | - | Expected version for exactly one enabled skill; mismatch stops execution |
| `include_shared_skills` | boolean | Yes | false | Include the `shared` space as read-only fallback |
| `max_steps` | number | Yes | 15 | Maximum execution rounds per call |
| `memory_turns` | number | Yes | 12 | Context turns to retain per call |
| `history_turns` | number | Yes | 3 | Cross-turn history injection rounds |
| `system_prompt` | string | No | - | Custom system prompt |
| `custom_variables` | string | No | - | JSON key-value pairs, e.g. `{"current_user":"Alice"}` |
| `verbose` | boolean | Yes | false | Debug mode: show commands, paths, parameters and command output |
| `allow_unsafe_commands` | boolean | Yes | false | Enables shells, installers and network clients for trusted self-hosted skills only |

### Usage in Dify

1. Install this plugin from the marketplace (or upload the `.difypkg` file)
2. For self-hosted users, set `Files_url` in Dify's `.env` to your Dify address
3. Arrange your workflow with the Skill Agent tool node
4. Set the same `skill_space` on Skill Manager and Skill Agent, then upload skill packages as zip files
5. Interact with Skill Agent

Skill Manager commands use stable names: `查看技能`, `新增技能`, `删除技能 <名称>`, and `下载技能 <名称>`.

### Skill Standard

- Each skill must include a `SKILL.md` (supports YAML Frontmatter: `name`, `description`)
- `SKILL.md` can define trigger conditions, workflows, reference files, script commands, deliverable specs, etc.
- Skill documents can use `${variable_name}` placeholders, values come from the `custom_variables` parameter

### FAQ

**1. Installation fails**
Try switching Dify's pip source. For intranet environments, use offline packages (contact the author).

**2. File transfer issues**
Check that Dify's `.env` has the correct `Files_url` matching your Dify address.

**3. No output from Skill Agent**
Ensure your LLM and provider plugin support function calling.

**4. Skill-related issues**
Ensure your skill materials and scripts are complete. For Node.js script skills, install Node.js in Dify's `plugin_daemon` container first.

**5. Trusted skills and high-risk commands**
By default, shell commands, package installation, and network download clients are blocked. Enable `allow_unsafe_commands` only when every installed skill and its dependencies are trusted, then explicitly add only the required executable to `allowed_commands`.

**6. Using custom_variables**
Pass a JSON string like `{"current_user":"Alice","team_id":"T123"}`. In SKILL.md or scripts, reference via `${current_user}` or environment variable `$CURRENT_USER`.

### Contact

- **Author:** [liux297](https://github.com/liux297)
- **Email:** 297218348@qq.com
- **Repository:** https://github.com/liux297/skill_agent

### License

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
