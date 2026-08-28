# Skill Agent

**Version:** 0.2.41 · **Type:** Dify tool plugin · **License:** Apache-2.0
**Author:** [liux297](https://github.com/liux297) · **Source:** [github.com/liux297/skill_agent](https://github.com/liux297/skill_agent)

[Simplified Chinese guide](readme/README_zh_Hans.md) · [Complete operations guide](GUIDE.md) · [Privacy policy](PRIVACY.md)

Skill Agent turns folders containing a `SKILL.md` into reusable, workflow-scoped capabilities. It lets Dify install skills, read instructions progressively, run controlled commands, stream progress, and return final text or generated files.

## Features

- Isolated **Skill Spaces** for independent workflows.
- Optional enabled-skill allow-lists, version pinning, and shared read-only fallback skills.
- Skill Manager commands for listing, adding, deleting, and downloading skills by name.
- Skill installation from uploaded ZIP files or a credential-free public `http(s)` ZIP URL.
- Custom runtime variables, conversation history, generated-file delivery, and concise streaming progress.
- Command allow-lists and an explicit unsafe-command switch for trusted self-hosted deployments.

![Workflow overview](_assets/workflow-overview.jpeg)

## Setup

1. Install the plugin from Dify Marketplace or upload its `.difypkg` package.
2. Add a Skill Manager node for administration and a Skill Agent node for user requests.
3. Give both nodes the same `skill_space` value.
4. Map the workflow question to `query`; map uploaded files when needed.
5. Connect Skill Agent `text` and `files` outputs to the final answer node.

## Skill Manager

![Skill Manager configuration](_assets/skill-manager-config.jpeg)

| Command | Example | Result |
|---|---|---|
| List | `list skills` | Lists skill folder names |
| Add | `add skill` | Installs from `files` or `archive_url` |
| Delete | `delete skill demo` | Deletes the named skill |
| Download | `download skill demo` | Returns the skill as a ZIP |

English aliases include `install skill`, `remove skill`, and `export skill`. Localized aliases are documented in the translated README. Uploaded files take precedence over `archive_url`. Existing skill folders are never overwritten automatically.

A valid archive contains a skill folder with `SKILL.md`:

```text
demo/
├── SKILL.md
├── Reference/
└── Scripts/
```

## Skill Agent

![Skill Agent configuration](_assets/skill-agent-config.jpeg)

Set `enabled_skills` to a comma-separated allow-list when the workflow must use specific skills. Use `skill_version` with exactly one enabled skill for fail-closed version checking. Pass trusted workflow identity and other context as a JSON object through `custom_variables`.

Keep `verbose=false` for concise end-user output. Enable it temporarily for diagnostics. Shells, package managers, Git, and network clients remain blocked unless the administrator enables unsafe commands and explicitly allow-lists each executable.

For every parameter, workflow recipe, update pattern, security control, output contract, and troubleshooting step, see the [complete operations guide](GUIDE.md).

## Privacy

The plugin processes prompts, selected skill instructions, uploaded files, custom variables, command output, and generated artifacts inside the configured Dify deployment. Skills may call external services only when their instructions and command policy permit it. See [PRIVACY.md](PRIVACY.md) for retention, sharing, and security details.
