---
name: claude-migrate
description: |
  Claude Code 一键迁移/备份 Skill（v2.0）。将所有积累（skills、memory、settings、.claude.json、rules、agents、commands、定时任务）备份到 Git 仓库，支持跨机器还原和定期远程推送。
  当用户想要备份、迁移、导出 Claude Code 配置和积累时使用。触发词包括但不限于：备份、迁移、backup、restore、migrate、搬家、换机器、一键迁移、导出配置、导入配置、备份我的配置、帮我打包、迁移到新机器、备份你的记忆技能、保存你的记忆、备份记忆。
  即使用户只是说"我要换机器了"或"帮我把这些东西保存下来"或"备份一下你的记忆和技能"，只要上下文暗示需要保存/迁移 Claude Code 的状态，都应该触发。
  不要用于普通的文件备份（用户只是想备份某个项目文件）、不要用于 git 操作（用户只是想 commit/push 代码）。
---

# Claude Code 一键迁移 v2.0

本 Skill 将 Claude Code 的**全部积累**备份到一个 Git 仓库中，支持跨机器一键还原和定期远程推送。

## 备份覆盖范围

| 内容 | 文件/路径 | essential | full |
|------|-----------|:---------:|:----:|
| 主配置 | `~/.claude.json`（项目授权、MCP服务器、使用偏好） | ✅ | ✅ |
| Settings | `~/.claude/settings.json`（环境变量、权限、hooks） | ✅ | ✅ |
| 全局 Memory | `~/.claude/CLAUDE.md` | ✅ | ✅ |
| Skills | `~/.claude/skills/`（所有已安装的 skill） | ✅ | ✅ |
| Rules | `~/.claude/rules/`（用户自定义规则） | ✅ | ✅ |
| Agents | `~/.claude/agents/`（自定义 agents） | ✅ | ✅ |
| Commands | `~/.claude/commands/`（自定义命令） | ✅ | ✅ |
| 定时任务 | `~/.claude/scheduled_tasks.json` | ✅ | ✅ |
| 项目级 Memory | `~/.claude/projects/*/CLAUDE.md` + 项目根目录的 CLAUDE.md | ✅ | ✅ |
| 命令历史 | `~/.claude/history.jsonl` | ❌ | ✅ |
| Plugins | `~/.claude/plugins/` | ❌ | ✅ |

## 核心脚本

```
python ~/.claude/skills/claude-migrate/scripts/migrate.py <command> [options]
```

## 五个命令

### 1. init — 初始化并配置远程仓库

```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py init --remote <git-url> [--git-user "名字"] [--git-email "邮箱"]
```

首次使用时运行。会创建 `~/.claude-backup/` git 仓库并配置 remote。之后 `backup --push` 就能直接推送。

### 2. backup — 备份当前配置

```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py backup [--tier essential|full] [--message "说明"] [--push]
```

- `--tier essential`（默认）：备份核心配置和所有 skill
- `--tier full`：上述 + 命令历史 + plugins
- `--push`：备份后推送到远程仓库
- 自动脱敏：token/密码/代理地址替换为 `__REDACTED__`
- Git-based skills 只存 remote URL（`.gitremote`），不拷贝 node_modules

### 3. restore — 还原配置

```bash
# 必须先 dry-run
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --dry-run
# 确认后实际执行
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --conflict <overwrite|skip|backup-existing>
```

### 4. status — 查看备份状态

```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py status
```

### 5. validate — 健康检查

```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py validate
```

## 使用场景

**用户说「备份一下你的记忆和技能」或「备份」**：
```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py backup --push
```

**用户说「我要换机器了」**：
1. 旧机器: `backup --push`
2. 新机器: `git clone <repo-url> ~/.claude-backup`
3. 新机器: `restore --dry-run` → 确认 → `restore --conflict backup-existing`
4. 新机器: `validate` → 手动填写脱敏字段

**用户首次配置远程仓库**：
```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py init --remote <url>
python ~/.claude/skills/claude-migrate/scripts/migrate.py backup --push
```
