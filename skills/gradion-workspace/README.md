# Gradion Workspace skill — Gradion

This bundle is a portable **skill**: a `SKILL.md` instruction file plus an
`openapi.yaml` your AI tool reads to call the Gradion Workspace API for
**Gradion** (https://workspace.gradion.com). Bundle version **1.9.0**.

## 1. Save your token

The bundle never includes your token — you keep that yourself. Save it once in
whichever password store you already use, and your AI tool will pick it up when
you run the skill.

**macOS Keychain:**

```bash
security add-generic-password -a "$USER" -s GRADION_API_TOKEN -w 'pat_…'   # paste yours
```

**1Password:** add a new item, give it a name you'll remember (e.g.
`GRADION_API_TOKEN`), and paste the `pat_…` value into the password field.

That's it — no environment variables to set up. When you run the skill, the AI
finds the token (or asks you where it is), and walks you through anything else
it needs, like which apps it can reach.

## 2. Install for your AI tool

### Claude Code & Claude Desktop
Unzip this bundle to `~/.claude/skills/gradion-workspace/` (or a project's
`.claude/skills/`). Claude auto-discovers `SKILL.md`. Restart the tool.

### Gemini CLI & Antigravity
These have no "skills" folder — point the tool at this bundle via its context
file. Append the contents of `SKILL.md` to `~/.gemini/GEMINI.md` (global) or a
project `GEMINI.md`, and keep `openapi.yaml` in the same directory. Antigravity:
add `SKILL.md` to its workspace rules/knowledge and keep `openapi.yaml` beside it.

### Codex CLI & Codex Desktop
Reference this bundle from `AGENTS.md` — global `~/.codex/AGENTS.md` or a
project-root `AGENTS.md` — and keep `openapi.yaml` alongside it.

## 3. Notes
- Treat the token like a password. Never commit it or paste it into chat.
- Read operations run silently; sending messages / calling app tools always
  asks for your confirmation first.
- If a request returns `400 skill_bundle_outdated`, re-download this bundle from
  **Preferences → API Tokens**.
