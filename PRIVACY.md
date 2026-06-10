## Privacy Policy

This privacy policy describes how **Skill Agent** (the "Plugin") processes data when used in Dify.

### 1. Who We Are

- **Maintainer:** liux297
- **Contact Email:** 297218348@qq.com
- **Origin:** This plugin is a derivative work based on [Skill Agent by lfenghx](https://github.com/lfenghx/skill_agent), licensed under Apache-2.0.

### 2. Data We Process

The Plugin may process the following data to provide its functionality:

- **User input**: the `query` parameter and related conversation context passed by Dify.
- **Custom variables**: the `custom_variables` parameter (JSON key-value pairs) optionally provided by the workflow caller to inject runtime context (e.g., user identity, team ID). These values are used only for template replacement in SKILL.md and as environment variables for subprocess commands within a single session.
- **Model selection/configuration**: the `model` selector and parameters used to call the LLM through Dify's model runtime.
- **Generated artifacts**: files created in the Plugin's temporary session directory during execution (e.g., `.txt`, `.md`, `.pdf`, images).
- **Operational logs**: debug logs printed by the Plugin runtime for troubleshooting (may include tool call names, file paths under the temp directory, and execution status). In non-verbose mode, detailed paths are redacted from user-visible output.

The Plugin does **not** intentionally collect personal data beyond what is required to execute the user's request.

### 3. How Data Is Used

Data is used strictly for:

- Selecting and invoking skills from the local `skills/` directory.
- Reading skill documentation (`SKILL.md`) and related skill files as needed.
- Replacing `${variable_name}` placeholders in SKILL.md with values from `custom_variables`.
- Running whitelisted commands (e.g., `python`, `node`) inside controlled directories to generate deliverables.
- Injecting custom variables as environment variables into subprocess command execution.
- Returning the final text and generated files back to Dify as tool outputs.
- Autonomous multi-step execution with minimal user confirmations: the agent completes all intermediate steps directly and only pauses to ask for user input at critical decision points (e.g., destructive operations or missing essential information).

### 4. Data Sharing & Third Parties

Depending on your Dify configuration, data may be transmitted to:

- **LLM providers configured in Dify**: The Plugin invokes the LLM via Dify's model runtime. Prompts, context (including custom variables), and conversation history may be sent to the configured provider to generate responses and tool plans.
- **Dify remote install/debug service (optional)**: If you use remote debugging install, plugin installation metadata may be exchanged with the configured remote install server.

The Plugin itself does not add additional third-party analytics/telemetry services.

### 5. Storage & Retention

- **Temporary files**: The Plugin creates a per-run temp session directory under the plugin workspace (e.g., `temp/dify-skill-xxxx/`). These files are used to assemble deliverables. The Plugin may clean up old sessions automatically based on its internal retention logic (keeps latest 4 sessions by default).
- **Conversation summary state (Dify storage)**: The Plugin may store a compact conversation summary and resume state in Dify's provided storage to support multi-turn runs.
- **Custom variables**: Stored only in memory during a single tool invocation session; not persisted beyond the session lifetime.

Retention is primarily controlled by:

- Your deployment environment (filesystem retention/backups)
- Your Dify configuration and storage lifecycle policies

### 6. Security

To reduce security risks:

- The Plugin restricts command execution to a whitelist of executables (`python`, `node`, `npm`, etc.).
- File reads/writes are constrained to approved directories (skill folder and temp session folder).
- User-visible output redacts absolute file paths to prevent information leakage.
- Custom variables are sanitized before use as environment variable keys (converted to uppercase, special chars replaced with underscores).

However, you should still treat generated files and logs as potentially sensitive if your inputs contain sensitive content.

### 7. Your Choices

- Avoid submitting sensitive personal information or secrets in `query` or `custom_variables` unless necessary.
- Manage/clear conversation data via Dify if your deployment requires data minimization.
- Remove plugin temp directories from disk if you need immediate cleanup in self-hosted deployments.
- Use verbose mode toggle to control how much detail is exposed in outputs.

### 8. Changes to This Policy

This policy may be updated as the Plugin evolves. Updates will be published in the repository.
