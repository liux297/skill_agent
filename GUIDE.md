# Skill Agent Operations Cookbook

This cookbook complements the complete [English README](README.md) and [Chinese guide](readme/README_zh_Hans.md). It provides copyable workflow patterns for common deployments.

## Recipe 1: Minimal question-answer workflow

Use this when administrators install the skill beforehand and end users only ask questions.

```text
Start(query, files, current_user)
  → Skill Agent
  → Answer(text, files)
```

Recommended Skill Agent settings:

| Setting | Value |
|---|---|
| `skill_space` | A unique workflow name, for example `support-assistant` |
| `enabled_skills` | The one production skill folder |
| `include_shared_skills` | `false` |
| `verbose` | `false` |
| `allow_unsafe_commands` | `false` |

Map the current user directly:

```json
{"current_user":"${current_user}"}
```

## Recipe 2: Business Assistant routing pattern

The documentation screenshots use this pattern:

```text
                         ┌─ management command ─→ Skill Manager ─→ Reply
Start → Conditional ─────┼─ update command ─────→ Download → Delete → Add → Reply
                         └─ other question ─────→ Skill Agent ─→ Reply(text + files)
```

Condition examples:

- Management: query contains `查看技能`, `新增技能`, `删除技能`, or `下载技能`
- Update: query contains `更新技能`
- Otherwise: normal Skill Agent request

Use the same `skill_space` on all Skill Manager and Skill Agent nodes.

## Recipe 3: Install from an uploaded ZIP

1. Add an `Array[File]` start variable.
2. Map it to Skill Manager `files`.
3. Set the fixed command to `新增技能` or route a user command.
4. Set `skill_space` to the target workflow library.
5. Return the Skill Manager text output.

The ZIP should contain a top-level skill folder with `SKILL.md`.

## Recipe 4: Install from a public ZIP URL

Use this for a public GitHub Release asset or repository archive.

| Skill Manager field | Value |
|---|---|
| `command` | `新增技能` |
| `skill_space` | Target workflow space |
| `files` | Empty |
| `archive_url` | Public credential-free `https://...zip` |

Uploaded files take precedence if both `files` and `archive_url` are provided.

## Recipe 5: Replace a production skill

Skill Manager intentionally refuses to overwrite an existing folder. Use an explicit replacement branch:

1. Validate the new ZIP in a staging Skill Space.
2. Run `下载技能 <name>` if a backup is required.
3. Run `删除技能 <name>` in the production space.
4. Run `新增技能` with the validated ZIP or public URL.
5. Run `查看技能` and a smoke-test question.

For zero-downtime rollout, install the new version under a new Skill Space, switch the workflow configuration, test, and then remove the old space later.

## Recipe 6: Isolate several workflows

| Workflow | `skill_space` | `enabled_skills` |
|---|---|---|
| Sales assistant | `sales-prod` | `sales-process` |
| Contract redaction | `contract-redaction-prod` | `contract-case-redaction` |
| Shared test flow | `assistant-staging` | empty or test allow-list |

Skill changes in one private space do not affect the others. Conversation history and temporary session keys are also scoped by space.

## Recipe 7: Add shared read-only skills

Use the reserved `shared` space for common helpers such as formatting or file conversion.

On Skill Agent:

```text
skill_space = sales-prod
include_shared_skills = true
```

Resolution order:

1. Search the private `sales-prod` space.
2. Fall back to `shared`.
3. If the same folder name exists in both, use the private skill.

Manage shared skills with a separate administrator workflow whose Skill Manager uses `skill_space=shared`.

## Recipe 8: Pin one skill version

Declare a version in `SKILL.md`:

```yaml
---
name: sales-process
description: Queries live sales-process data.
version: 3.4.1
---
```

Configure:

```text
enabled_skills = sales-process
skill_version = 3.4.1
```

The invocation stops before execution when the installed version is missing or different. Version pinning requires exactly one enabled skill.

## Recipe 9: Pass the authenticated user

Map the workflow's trusted identity variable into `custom_variables`:

```json
{
  "iv-user": "${sys.user_id}",
  "team_id": "${team_id}"
}
```

Inside a skill:

- Text template: `${iv-user}`
- Session context: `get_session_context()`
- Subprocess environment: `IV_USER` and `TEAM_ID`

The skill should use the provided identity by default and should not ask the user to confirm it again.

## Recipe 10: Generate and return files

1. Upload input files through the Skill Agent `files` parameter if needed.
2. The skill reads the normalized upload paths from session context.
3. Write generated content into the temporary session directory.
4. Mark/export the intended file as a deliverable.
5. Connect Skill Agent `files` to the Dify answer node.

Never assume that creating a temporary file automatically exposes it to the user; it must be marked for delivery and mapped to the answer output.

## Recipe 11: Tune memory and output size

| Scenario | `memory_turns` | `history_turns` | `max_stdout_chars` |
|---|---:|---:|---:|
| One-shot document conversion | 6 | 0 | 6000–12000 |
| Business assistant | 6–12 | 3–8 | 12000–30000 |
| Large structured API response | 8–12 | 3 | 30000, with filtering in the skill |

Prefer returning filtered JSON or a concise table instead of increasing the output cap indefinitely.

## Recipe 12: Use safe and unsafe commands

Safe production example:

```text
allowed_commands = python,python3
allow_unsafe_commands = false
```

Trusted self-hosted build example:

```text
allowed_commands = python,python3,pip,git,curl
allow_unsafe_commands = true
```

Unsafe mode should only be enabled when the skill source, dependencies, and every uploaded input are trusted. The plugin still intersects the requested list with its recognized command sets.

## Recipe 13: Write a useful system prompt

Keep only cross-skill behavior in the node:

```text
Use installed skills for business questions.
Query live systems for project, task, approval, and workflow data.
Do not invent unavailable values. Prefer concise tables and lists.
```

Keep the following in `SKILL.md`, not the node system prompt:

- API endpoints and authentication rules
- Script paths and arguments
- Field mappings and status definitions
- Detailed process steps
- Output templates and domain examples

## Recipe 14: Debug a failing skill

Temporarily set `verbose=true`, then verify in order:

1. The expected skill appears in `查看技能`.
2. `skill_space` and `enabled_skills` exactly match the folder name.
3. `skill_version` matches the declared version.
4. The model reads `SKILL.md` before skill files or commands.
5. The executable is recognized and allowed.
6. Uploaded-file URLs are reachable from the plugin runtime.
7. Command output is not being truncated by `max_stdout_chars`.
8. The generated file is marked and connected to the answer `files` output.

Return `verbose=false` before publishing the workflow to end users.

## Pre-publish checklist

- [ ] Skill Manager and Skill Agent use the same Skill Space.
- [ ] Production uses an explicit `enabled_skills` allow-list.
- [ ] Current user comes from a trusted workflow variable.
- [ ] The system prompt is short; detailed behavior lives in `SKILL.md`.
- [ ] Unsafe commands are disabled or narrowly justified.
- [ ] Both `text` and `files` outputs are connected when files may be generated.
- [ ] List, normal query, missing data, command rejection, and file delivery have been tested.
- [ ] `verbose` is disabled for end-user runs.
