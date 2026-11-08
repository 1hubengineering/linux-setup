# Install and remove AI skills

[User guides](README.md) · [Commands](commands.md)

Run `skills` to install, list, or remove local skills. From a checkout that
has not been installed, run `python3 scripts/skill_manager.py` instead. Select
Codex or Claude Code, then choose all your projects or one project. For one project, provide
the path of an existing project directory; enter `.` to use the current directory.
Choose one or more work areas, such as Web development and UI and UX.
Skills matching any selected area are shown once. Move with the arrow keys,
toggle areas or skills with Space, and press Enter to confirm. Enter without
checking anything selects nothing; Esc goes back. Choose All skills to browse
the whole catalog for your agent.

| Agent | Global directory | Project directory |
| --- | --- | --- |
| Codex | `~/.agents/skills/` | `<project>/.agents/skills/` |
| Claude Code | `~/.claude/skills/` | `<project>/.claude/skills/` |

These are local agent skills, not skills uploaded to ChatGPT or another hosted
service. The manager lists and removes skill directories in the selected location,
including skills installed by other tools; it displays the exact paths and asks
for confirmation before deleting. It does not overwrite existing skills. Skills
installed as symlinks are removed by unlinking them; their targets are kept. Skills
in other discovery locations, such as `~/.codex/skills`, are not listed there.

The catalog includes UI/UX Pro Max, Humanizer, frontend design, web guidelines,
React, testing, DevOps, and writing skills. OpenAI's Codex-specific skills are
offered only for Codex. The catalog records upstream repositories and commit
IDs in [`skills.catalog.json`](../skills.catalog.json). Downloads need network
access; files are then installed locally with their supporting resources. UI/UX
Pro Max's plugin-specific script paths are adapted to the selected installation
directory, so reinstall it after moving that directory. Review the displayed
source URLs: third-party skills contain instructions and may include scripts.
Restart the agent session if it does not immediately discover new skills.


## Remove skills

Open `skills`, choose **Review or remove installed skills**, then select
your AI app and where the skills are installed. Move with the arrows and check the skills to remove with
Space. Press Enter to review their exact paths, then confirm removal. Leave
everything unchecked or press Esc to leave the directory unchanged.
