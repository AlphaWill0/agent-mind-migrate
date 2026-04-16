<div align="center">

# 🧠 agent-mind-migrate

**Migrate your AI agent's mind to a new machine — skills, memory, config, everything.**

One command to backup. One command to restore. Zero dependencies.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

[English](#-what-it-does) · [中文](#-中文说明)

</div>

---

## 💡 The Problem

You've spent weeks teaching your AI agent. Custom skills, carefully tuned settings, accumulated memory, rules, commands, cron jobs. Then you switch machines — and it's all gone. Starting from scratch.

**agent-mind-migrate** solves this. It backs up your AI agent's entire "mind" — everything that makes it *yours* — into a Git repo. Switch machines, restore in seconds.

## 🤖 What It Does

| Feature | Description |
|---------|-------------|
| **Multi-Agent** | Supports Claude Code, OpenClaw, Hermes — more coming |
| **Auto-Discovery** | Detects which agents are installed, backs up all of them |
| **One Command** | `backup --push` to save, `restore` to bring it back |
| **Smart Redaction** | API keys and tokens are automatically replaced with `__REDACTED__` |
| **Smart Restore** | Won't overwrite your existing secrets with placeholders |
| **Atomic Writes** | Staging directory + three-step rename — crash-safe |
| **Integrity Check** | SHA-256 hash for every file, verified on restore |
| **Selective Restore** | Restore only skills, only memory, only one agent — your choice |
| **Zero Dependencies** | Python 3.8+ standard library + Git CLI. That's it. |
| **Cross-Platform** | Windows / macOS / Linux |

## ⚡ Quick Start

### Install

```bash
# Clone into your Claude Code skills directory
git clone https://github.com/AlphaWill0/agent-mind-migrate.git ~/.claude/skills/agent-mind-migrate
```

### First-Time Setup

```bash
# Point to your backup repo (create one first, e.g. agent-mind-backup)
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py init --remote <your-backup-repo-url>
```

### Daily Backup

Just say to Claude Code:

```
备份一下
```

Or run manually:

```bash
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py backup --push
```

### Migrate to a New Machine

```bash
# On the new machine:
git clone <your-backup-repo-url> ~/.claude-backup
git clone https://github.com/AlphaWill0/agent-mind-migrate.git ~/.claude/skills/agent-mind-migrate
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py restore --dry-run
# Review the output, then:
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py restore --conflict backup-existing
```

Done. Your agent remembers everything.

## 📦 What Gets Backed Up

### Claude Code (`~/.claude/`)

| Content | Essential | Full |
|---------|:---------:|:----:|
| Main config (`.claude.json`) | ✅ | ✅ |
| Settings, environment variables | ✅ | ✅ |
| Global memory (`CLAUDE.md`) | ✅ | ✅ |
| All installed skills | ✅ | ✅ |
| Rules, agents, commands | ✅ | ✅ |
| Scheduled tasks, usage stats | ✅ | ✅ |
| Project-level memory | ✅ | ✅ |
| Command history | — | ✅ |
| Plans, plugins | — | ✅ |

### OpenClaw (`~/.openclaw/`)

Config, bot settings, memory (SQLite), cron jobs, extensions, devices. Credentials excluded. Auth fields redacted.

### Hermes (`~/.hermes/`)

Config, identity (SOUL.md), memories, skills, cron. Sensitive files (`.env`, `auth.json`) excluded.

## 🗂️ Backup Structure

Each agent gets its own directory — clean separation, no conflicts:

```
your-backup-repo/
├── manifest.json          # Which agents, when, integrity hashes
├── claude-code/           # Claude Code backup
│   ├── claude.json
│   ├── settings.json
│   ├── CLAUDE.md
│   ├── skills/
│   ├── rules/
│   └── ...
├── openclaw/              # OpenClaw backup (when detected)
│   ├── openclaw.json
│   ├── memory/
│   └── ...
└── hermes/                # Hermes backup (when detected)
    ├── config.yaml
    ├── SOUL.md
    └── ...
```

Each agent directory is only created when that agent is detected on your machine. Backward compatible: v3.x backups (flat structure) are auto-detected as Claude Code.

## 🔧 Commands

| Command | What It Does |
|---------|-------------|
| `init --remote <url>` | Set up remote Git repo |
| `backup [--push]` | Backup all detected agents |
| `backup --agents claude-code` | Backup only specific agents |
| `backup --tier full` | Include history, plans, plugins |
| `restore --dry-run` | Preview what will be restored |
| `restore --conflict backup-existing` | Restore (backup existing files first) |
| `restore --agents openclaw` | Restore only one agent |
| `restore --only skills memory` | Restore specific modules |
| `status` | Show backup status per agent |
| `validate` | Health check |

## 🔒 Security

- **Auto-redaction**: API keys, tokens, passwords → `__REDACTED__` before commit
- **Smart merge**: On restore, if a field is `__REDACTED__` but your machine already has the real value, it keeps the real value
- **Path traversal protection**: Restore targets must be under `$HOME`
- **File lock**: Prevents concurrent backup/restore operations
- **No secrets in Git**: Credentials directories are always excluded

## 🌍 Supported Agents

| Agent | Config Dir | Status |
|-------|-----------|--------|
| Claude Code | `~/.claude/` | ✅ Full support |
| OpenClaw | `~/.openclaw/` | ✅ Full support |
| Hermes | `~/.hermes/` | ✅ Full support |

The plugin architecture makes it easy to add more agents. PRs welcome!

## 📋 Requirements

- Python 3.8+ (standard library only, zero `pip install`)
- Git CLI
- Windows / macOS / Linux

## 🇨🇳 中文说明

**agent-mind-migrate** 是一个多 AI Agent 统一迁移工具。

你花了几周调教 AI Agent——技能、记忆、设置、规则全都配好了。然后换台电脑，一切归零。

这个工具把 Agent 的「心智」——技能、记忆、配置、规则、命令、定时任务——全部备份到 Git 仓库。换机器时一条命令还原，Agent 记住一切。

### 支持的 Agent

- **Claude Code** — 完整备份（配置、技能、记忆、规则、命令等）
- **OpenClaw** — 完整备份（配置、Bot、记忆、插件、设备等）
- **Hermes** — 完整备份（配置、身份、记忆、技能、定时任务）

### 使用方式

```bash
# 安装
git clone https://github.com/AlphaWill0/agent-mind-migrate.git ~/.claude/skills/agent-mind-migrate

# 配置远程仓库
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py init --remote <你的仓库URL>

# 备份（或直接对 Claude Code 说"备份一下"）
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py backup --push

# 换机器还原
git clone <备份仓库URL> ~/.claude-backup
git clone https://github.com/AlphaWill0/agent-mind-migrate.git ~/.claude/skills/agent-mind-migrate
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py restore --dry-run
python3 ~/.claude/skills/agent-mind-migrate/scripts/migrate.py restore --conflict backup-existing
```

### 特色

- 🔍 自动发现本机已安装的 Agent
- 🔐 自动脱敏（token/密码 → `__REDACTED__`）
- 🧠 智能合并还原（不覆盖本机已有的真实密钥）
- ⚛️ 原子写入（中途失败自动回滚）
- 🔢 SHA-256 完整性校验
- 📦 零外部依赖（仅需 Python 3.8+ 和 Git）

---

## License

MIT

---

<div align="center">

**Your agent's mind deserves a backup plan.**

Made with ❤️ by [AlphaWill](https://github.com/AlphaWill0)

</div>
