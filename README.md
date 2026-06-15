## Skill Agent

**Author:** [liux297](https://github.com/liux297) · 297218348@qq.com
**Version:** 0.2.5 | **Type:** Tool Plugin | **License:** Apache-2.0
**Repository:** https://github.com/liux297/skill_agent

---

### Introduction

Skill Agent is a general-purpose tool plugin built on the **Skill Progressive Disclosure** pattern, inspired by the OpenClaw and Hermes agent architectures. It treats the local `skills/` directory as a modular toolbox: the model reads a skill index first, then loads the relevant `SKILL.md` manual on demand, and finally reads reference files or runs scripts only when necessary — delivering text or files as the final output.

---

### What's New in v0.2.5

- **Custom Variables (`custom_variables`)** — Inject JSON key-value pairs into the agent context. Skills access them via `get_session_context()`. Supports `${var}` template replacement in SKILL.md and environment variable injection for subprocess commands.
- **Verbose Mode (`verbose`)** — Toggle between detailed tool execution progress (for debugging) and clean user-facing output (for production).
- **Custom System Prompt (`system_prompt`)** — Override or extend the default agent behavior instructions.
- **Optimized Progressive Disclosure** — When SKILL.md already specifies an executable entry point, the agent executes directly without redundant `list_skill_files` calls.
- **Smart Command Coercion** — Automatically converts string commands to arrays and strips backticks accidentally copied from Markdown code blocks.
- **Structured Output Formatting** — JSON results from commands are automatically converted to structured natural-language summaries.
- **Enhanced Diagnostics** — Improved error messages for DNS/network failures and empty stdout to help the LLM self-diagnose issues.
- **Model Capability Detection** — Adaptive detection of model function-calling support, with automatic fallback between Function Calling and JSON protocol (inspired by OpenClaw/Hermes).
- **Unified Tool Execution Pipeline** — Single execution path eliminates duplicate FC/JSON logic.
- **Token-Aware Context Compaction** — Smart context compression based on token estimation with automatic recovery from context overflow.
- **Smart JSON Compression** — Intelligent JSON summarization replaces naive truncation.
- **Streaming Output with Protocol Filtering** — Real-time natural-language streaming while internal JSON protocol messages are hidden from users.
- **Step-by-Step Process Visualization** — Categorized icons, step numbering, and configurable verbose toggle.
- **Command Whitelist Sandbox** — Secure script execution within a configurable command whitelist.

---

### Use Cases

- Integrate Skills and constrain/strengthen the model using "manual (SKILL.md) + file structure + scripts"
- Show progress messages and return generated files as tool outputs
- Package capabilities as reusable skill folders (References, Scripts, etc.) instead of hard-coding everything in prompts
- Inject runtime context (user identity, team ID, etc.) into skills via `custom_variables`

---

### Features

- **Progressive Disclosure:** skill index → read `SKILL.md` → read files / run commands as needed
- **File Delivery:** all files in the temp session directory are returned when the agent finishes
- **Free Execution:** the agent can run any whitelisted command (read/write files, execute scripts, etc.)
- **Controllable Memory:** configurable memory turns and max step depth
- **Custom Variables:** inject runtime context via `${var}` templates and environment variables
- **Verbose Mode Toggle:** switch between debug-level detail and clean user-facing output

---

### Tool Parameters

This plugin provides two tools:

- **Skill Manager** — Manages the local skills directory (list / add / delete / download skills).
  ![Skill Manager](_assets/image-0.png)
- **agent_skill** — A general agent that executes stored skills.
  ![agent_skill](_assets/image-1.png)

The **agent_skill** tool accepts the following parameters:

| Parameter | Type | Required | Default | Description |
|------|------|------|--------|------|
| `query` | string | Yes | - | Your question or task for the agent |
| `model` | model-selector | Yes | - | LLM to run this tool |
| `files` | files | No | - | File(s) for the agent to process |
| `max_steps` | number | Yes | 15 | Max reasoning/tool steps per call |
| `memory_turns` | number | Yes | 12 | Recent turns to keep during the run |
| `history_turns` | number | Yes | 3 | Previous runs to inject as transcript |
| `system_prompt` | string | No | - | Custom system prompt to override defaults |
| `custom_variables` | string | No | - | JSON key-value pairs, e.g. `{"current_user":"Alice"}` |
| `verbose` | boolean | Yes | true | Show detailed execution progress |

The `custom_variables` parameter accepts a JSON object of key-value pairs that will be injected into the agent context. Skills can access these variables via `get_session_context()`, making it easy to pass user identity, team info, or other runtime context to skills.

---

### How to Use (in Dify)

**Step 1:** Install this plugin from the Marketplace (or upload the `.difypkg` file)

**Step 2:** For self-hosted deployments, set `Files_url` in Dify's `.env` to your Dify address, otherwise Dify cannot fetch uploaded files

**Step 3:** Build your workflow as shown below
![Workflow](_assets/image-2.png)

**Step 4:** Manage skills (upload skill packages as zip files)
![Manage Skills](_assets/image-3.png)

**Step 5:** Chat with Skill Agent
![Chat 1](_assets/image-4.png)
![Chat 2](_assets/image-5.png)

---

### Skill Standard

- Every skill must include `SKILL.md` (YAML frontmatter supported: `name`, `description`)
- `SKILL.md` can define trigger conditions, workflow, required reference reads, commands to run, and deliverable specs
- Skills can use `${variable_name}` placeholders that are replaced by values from `custom_variables`

---

### Changelog

**v0.2.5 (current):**
1. `custom_variables` JSON key-value injection with template replacement and environment variable pass-through
2. `verbose` mode toggle for debug or user-facing output
3. `system_prompt` parameter to override default agent instructions
4. Optimized progressive disclosure: skip redundant file listing when entry point is specified
5. Auto string-to-array command coercion with backtick cleanup
6. Auto JSON-to-natural-language structured summary
7. Enhanced diagnostics for DNS/network failures and empty stdout
8. Adaptive model capability detection (FC / JSON protocol auto-switch, OpenClaw/Hermes inspired)
9. Unified tool execution pipeline eliminating duplicate FC/JSON paths
10. Token-aware context compaction with automatic overflow recovery
11. Smart JSON compression replacing naive truncation
12. Real-time streaming output with internal protocol filtering
13. Step-by-step process visualization with categorized icons and step numbering
14. Command whitelist sandbox for secure script execution

**Earlier versions:** Streaming output, multi-turn conversations, file memory, file uploads, auto dependency installation, skill management, and the core progressive disclosure architecture.

---

### FAQ

**1. Installation issues**
If installation fails with network access available, try switching Dify's pip mirror for better dependency downloads. In intranet environments, install via an offline package (contact the author).

**2. File transfer issues**
If uploading/downloading files fails (wrong URL, download timeout, etc.), check whether Dify's `.env` has `Files_url` set correctly and matches your Dify address.

**3. No output from skill_agent**
Make sure your model and provider plugin support function calling.

**4. Skill invocation issues**
The more complete your skill is, the more smoothly the agent can invoke it. Ensure your skill materials and scripts are not missing. For Node.js script skills, install Node.js in the Dify `plugin_daemon` container first.

**5. Using custom_variables**
Pass a JSON string like `{"current_user":"Alice","team_id":"T123"}`. Reference variables as `${current_user}` in SKILL.md or via environment variables (auto uppercased: `$CURRENT_USER`).

---

### Author & Contact

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
