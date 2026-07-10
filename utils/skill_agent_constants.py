RESUME_KEY_PREFIX = "skill:resume:"
HISTORY_KEY_PREFIX = "skill:history:"
SESSION_DIR_KEY_PREFIX = "skill:session_dir:"

HISTORY_TRANSCRIPT_MAX_CHARS = 6000

# Commands enabled in the normal mode.  This is deliberately a small set: shells,
# package managers and network clients turn a command allow-list into arbitrary
# code execution / data exfiltration very quickly.
ALLOWED_COMMANDS = {"python", "python3", "node", "pandoc", "soffice", "pdftoppm"}
UNSAFE_COMMANDS = {
    "bash", "sh", "/bin/bash", "/bin/sh", "pip", "pip3", "npm", "npx",
    "bun", "uv", "uvx", "curl", "wget", "git",
}
TEMP_SESSION_PREFIX = "dify-skill-"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
