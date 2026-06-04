## Skill Agent

**Author:** lfenghx  
**Version:** 0.0.4  
**Type:** Tool (Plugin)

### Introduction

Skill Agent is a general-purpose tool plugin based on “Skill Progressive Disclosure”. It treats the local `skills/` directory as a toolbox, so the model can read the skill manual on demand, then read files / run scripts only when necessary, and finally deliver text or files.

### Use Cases

- You want to integrate Skills and constrain/strengthen the model using “manual (SKILL.md) + file structure + scripts”
- You want progress messages and to return generated files as tool outputs
- You want to package capabilities as reusable skill folders (Reference, Scripts, etc.) instead of hard-coding everything in prompts

### Features

- Progressive disclosure: skill index → read `SKILL.md` → read files / run commands as needed
- File delivery: all files in the temp session directory are returned when the agent finishes
- Free execution: the agent can execute commands such as reading/writing files and running scripts
- Controllable memory: configurable memory turns and max step depth

### Tool Parameters

This plugin provides two tools:

- “Skill Manager”: manages the local skills directory (list/add/delete skills)
  ![alt text](_assets/image-0.png)
- "agent_skill": a general agent that can execute skills that have been stored
  ![alt text](_assets/image-1.png)

The "agent_skill" tool accepts a `custom_variables` parameter — a JSON object of key-value pairs (e.g. `{"current_user":"Alice","team_id":"T123"}`) that will be injected into the agent context. Skills can access these variables via the `get_session_context()` action, making it easy to pass user identity, team info, or other runtime context to skills.

### How to Use (in Dify)

Step 1: Install this plugin directly from the Marketplace  
Step 2: For self-hosted deployments, set `Files_url` in Dify’s `.env` to your Dify address, otherwise Dify cannot fetch uploaded files  
Step 3: Build your workflow as shown below  
![alt text](_assets/image-2.png)  
Step 4: Manage skills  
![alt text](_assets/image-3.png)  
Step 5: Chat with Skill Agent  
![alt text](_assets/image-4.png)

Video tutorial: https://www.bilibili.com/video/BV1iszkBCEes

### Skill Standard

- Every skill must include `SKILL.md` (YAML frontmatter supported: `name`, `description`)
- `SKILL.md` can define trigger conditions, workflow, required reference reads, commands to run, and deliverable specs

### Changelog

- 0.0.3:
  1. Support agent streaming output
  2. Support interactive, multi-turn conversations across turns
  3. Support file memory (no need to re-upload repeatedly)
  4. Support running Node.js scripts as skills
  5. Improve skill_agent runtime stability
- 0.0.2: Support agent file upload and parsing; support automatic dependency installation
- 0.0.1: Implement skill management and a general agent that works with progressive disclosure

### FAQ

1. Installation issues  
   If installation fails with network access available, try switching Dify's pip mirror for better dependency download performance. In intranet environments, install via an offline package (contact the author).

2. File transfer issues  
   If uploading/downloading files fails (e.g., incorrect URL, download timeout), check whether Dify's `.env` has `Files_url` set correctly and whether it matches your Dify address.

3. No output from skill_agent  
   This is usually due to the model. Make sure your model and provider plugin support function calling. The author recommends DeepSeek-V3.1 and reports good test results.

4. Skill invocation issues  
   The more complete your skill is, the more smoothly the agent can invoke it. Ensure your skill materials and scripts are not missing. For Node.js-script skills, install a Node.js runtime in Dify’s `plugin_daemon` container first.

### Author & Contact

- GitHub: lfenghx (repo: <https://github.com/lfenghx/skill_agent>)
- Bilibili: 元视界\_O凌枫o
- Email: 550916599@qq.com
