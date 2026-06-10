## Skill Agent

**Author:** liux297
**Version:** 0.1.0
**Type:** Tool (Plugin)
**License:** Apache-2.0

### Acknowledgements & Origin

This plugin is a derivative work based on [Skill Agent by lfenghx](https://github.com/lfenghx/skill_agent) (originally licensed under Apache-2.0). We extend our sincere thanks to the original author for the excellent foundation.

If the original author has any concerns about this derivative work, please contact us promptly at 297218348@qq.com and we will address them immediately.

### What's New in This Version

This version includes meaningful enhancements on top of the original:

- **Custom Variables (`custom_variables`)**: Inject JSON key-value pairs into agent context; skills can access them via `get_session_context()`. Supports `${var}` template replacement in SKILL.md and environment variable injection for subprocess commands.
- **Verbose Mode (`verbose`)**: Toggle between detailed tool execution progress (for debugging) and clean user-facing output (for production).
- **Custom System Prompt (`system_prompt`)**: Override or extend default agent behavior instructions.
- **Optimized Progressive Disclosure**: When SKILL.md already specifies an executable entry point, the agent can execute directly without redundant `list_skill_files` calls.
- **Smart Command Coercion**: Automatically converts string commands to arrays and strips backticks accidentally copied from Markdown code blocks.
- **Structured Output Formatting**: Command results returned as JSON are automatically converted to structured natural-language summaries.
- **Enhanced Diagnostics**: Improved error messages for DNS/network failures and empty stdout to help the LLM self-diagnose issues.
- **Minimized Intermediate Confirmations**: The agent autonomously completes all intermediate steps without unnecessary user confirmations, only pausing at critical decision points (e.g., destructive operations) or when essential information is missing.

### Introduction

Skill Agent is a general-purpose tool plugin based on "Skill Progressive Disclosure". It treats the local `skills/` directory as a toolbox, so the model can read the skill manual on demand, then read files / run scripts only when necessary, and finally deliver text or files.

### Use Cases

- You want to integrate Skills and constrain/strengthen the model using "manual (SKILL.md) + file structure + scripts"
- You want progress messages and to return generated files as tool outputs
- You want to package capabilities as reusable skill folders (Reference, Scripts, etc.) instead of hard-coding everything in prompts
- You want to inject runtime context (user identity, team ID, etc.) into skills via custom variables

### Features

- Progressive disclosure: skill index -> read `SKILL.md` -> read files / run commands as needed
- File delivery: all files in the temp session directory are returned when the agent finishes
- Free execution: the agent can execute commands such as reading/writing files and running scripts
- Controllable memory: configurable memory turns and max step depth
- Custom variables: inject runtime context into skills via `${var}` templates and environment variables
- Verbose mode: switch between debug-level detail and clean user-facing output

### Tool Parameters

This plugin provides two tools:

- **"Skill Manager"**: manages the local skills directory (list/add/delete/download skills)
  ![alt text](_assets/image-0.png)
- **"agent_skill"**: a general agent that can execute skills that have been stored
  ![alt text](_assets/image-1.png)

The "agent_skill" tool accepts the following parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | - | Your question or task for the agent |
| `model` | model-selector | Yes | - | LLM to run this tool |
| `files` | files | No | - | File(s) for the agent to process |
| `max_steps` | number | Yes | 15 | Max reasoning/tool steps per call |
| `memory_turns` | number | Yes | 12 | Recent turns to keep during the run |
| `history_turns` | number | Yes | 3 | Previous runs to inject as transcript |
| `system_prompt` | string | No | - | Custom system prompt to override defaults |
| `custom_variables` | string | No | - | JSON key-value pairs, e.g. `{"current_user":"Alice"}` |
| `verbose` | boolean | Yes | true | Show detailed execution progress |

The `custom_variables` parameter accepts a JSON object of key-value pairs that will be injected into the agent context. Skills can access these variables via the `get_session_context()` action, making it easy to pass user identity, team info, or other runtime context to skills.

### How to Use (in Dify)

**Step 1**: Install this plugin from the Marketplace (or upload `.difypkg` file)

**Step 2**: For self-hosted deployments, set `Files_url` in Dify's `.env` to your Dify address, otherwise Dify cannot fetch uploaded files

**Step 3**: Build your workflow as shown below
![alt text](_assets/image-2.png)

**Step 4**: Manage skills (upload skill packages as zip files)
![alt text](_assets/image-3.png)

**Step 5**: Chat with Skill Agent
![alt text](_assets/image-4.png)
![alt text](_assets/image-5.png)

### Skill Standard

- Every skill must include `SKILL.md` (YAML frontmatter supported: `name`, `description`)
- `SKILL.md` can define trigger conditions, workflow, required reference reads, commands to run, and deliverable specs
- Skills can use `${variable_name}` placeholders that are replaced by values from `custom_variables`

### Changelog

**v0.1.0 (this version):**
1. Add `custom_variables` parameter for runtime context injection with template replacement and env var support
2. Add `verbose` mode toggle for clean user-facing output
3. Add `system_prompt` parameter for custom agent behavior overrides
4. Optimize progressive disclosure rule: skip redundant file listing when SKILL.md specifies executable entry
5. Add auto coercion of string commands to arrays with backtick stripping
6. Add structured JSON-to-natural-language formatting for command output
7. Enhance diagnostics for DNS failures and empty stdout
8. Add minimal-confirmation principle: agent completes all steps autonomously, only pausing at critical decisions
9. Version bump to 0.1.0

**v0.0.3 (original by lfenghx):**
1. Support agent streaming output
2. Support interactive, multi-turn conversations across turns
3. Support file memory (no need to re-upload repeatedly)
4. Support running Node.js scripts as skills
5. Improve skill_agent runtime stability

**v0.0.2 (original):** Support agent file upload and parsing; support automatic dependency installation

**v0.0.1 (original):** Implement skill management and a general agent that works with progressive disclosure

### FAQ

**1. Installation issues**
If installation fails with network access available, try switching Dify's pip mirror for better dependency download performance. In intranet environments, install via an offline package (contact the author).

**2. File transfer issues**
If uploading/downloading files fails (e.g., incorrect URL, download timeout), check whether Dify's `.env` has `Files_url` set correctly and whether it matches your Dify address.

**3. No output from skill_agent**
This is usually due to the model. Make sure your model and provider plugin support function calling. The original author recommends DeepSeek-V3.1 and reports good test results.

**4. Skill invocation issues**
The more complete your skill is, the more smoothly the agent can invoke it. Ensure your skill materials and scripts are not missing. For Node.js-script skills, install a Node.js runtime in Dify's `plugin_daemon` container first.

**5. Using custom_variables**
Pass a JSON string like `{"current_user":"Alice","team_id":"T123"}` in the `custom_variables` field. Inside your SKILL.md or scripts, reference variables as `${current_user}` or access them via environment variables (converted to uppercase: `$CURRENT_USER`).

### Author & Contact

- **Email:** 297218348@qq.com
- **Original Author:** [lfenghx](https://github.com/lfenghx) — we gratefully build upon their work under the Apache-2.0 license

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

---

**Original work copyright:** Copyright (c) 2026 lfenghx — see [original repository](https://github.com/lfenghx/skill_agent) for details.
