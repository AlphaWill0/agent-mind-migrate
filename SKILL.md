---
name: claude-migrate
description: |
  Claude Code 一键备份/迁移 Skill。将所有积累（skills、memory、settings、.claude.json、rules、agents、commands、定时任务、使用统计、规划方案）备份到 Git 仓库，支持跨机器一键还原和远程推送。
  当用户想要备份、迁移、导出 Claude Code 配置和积累时使用。触发词包括但不限于：备份、迁移、backup、restore、migrate、搬家、换机器、一键迁移、导出配置、导入配置、备份我的配置、帮我打包、迁移到新机器、备份你的记忆技能、保存你的记忆、备份记忆。
  即使用户只是说"我要换机器了"或"帮我把这些东西保存下来"或"备份一下你的记忆和技能"，只要上下文暗示需要保存/迁移 Claude Code 的状态，都应该触发。
  不要用于普通的文件备份（用户只是想备份某个项目文件）、不要用于 git 操作（用户只是想 commit/push 代码）。
metadata:
  category: custom
  author: weiwancheng
---

# Claude Code 一键迁移 v3.4

本 Skill 将 Claude Code 的**全部积累**备份到一个 Git 仓库中，支持跨机器一键还原和定期远程推送。跨平台支持 Windows / macOS / Linux。

## 备份覆盖范围

| 内容 | 文件/路径 | essential | full |
|------|-----------|:---------:|:----:|
| 主配置 | `~/.claude.json`（项目授权、MCP服务器、使用偏好） | Y | Y |
| Settings | `~/.claude/settings.json`（环境变量、权限、hooks） | Y | Y |
| 全局 Memory | `~/.claude/CLAUDE.md` | Y | Y |
| Skills | `~/.claude/skills/`（所有已安装的 skill） | Y | Y |
| Rules | `~/.claude/rules/`（用户自定义规则） | Y | Y |
| Agents | `~/.claude/agents/`（自定义 agents） | Y | Y |
| Commands | `~/.claude/commands/`（自定义命令） | Y | Y |
| 定时任务 | `~/.claude/scheduled_tasks.json` | Y | Y |
| 使用统计 | `~/.claude/stats-cache.json` | Y | Y |
| 项目级 Memory | `~/.claude/projects/*/CLAUDE.md` + 项目根目录的 CLAUDE.md | Y | Y |
| 命令历史 | `~/.claude/history.jsonl` | - | Y |
| 规划方案 | `~/.claude/plans/*.md`（Agent 规划文档） | - | Y |
| Plugins | `~/.claude/plugins/` | - | Y |

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

- `--tier essential`（默认）：核心配置 + skills + memory + rules + agents + commands + 定时任务 + 统计
- `--tier full`：上述 + 命令历史 + plugins + 规划方案（换机器时推荐）
- `--push`：备份后推送到远程仓库（**网络外发操作，执行前告知用户**）
- 自动脱敏：token/密码/代理地址替换为 `__REDACTED__`
- Git-based skills 只存 remote URL（`.gitremote`），不拷贝 node_modules
- 原子写入：通过 staging 目录保证备份完整性
- SHA-256 哈希：每个文件的哈希值记录在 manifest.json 中

### 3. restore — 还原配置

```bash
# 必须先 dry-run
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --dry-run
# 确认后实际执行
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --conflict <overwrite|skip|backup-existing>
# 只还原指定模块
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --conflict backup-existing --only skills memory config
```

可选模块名：config, memory, skills, rules, agents, commands, scheduled_tasks, stats, plans, history, plugins, project_memories

**智能合并**：settings.json 和 .claude.json 还原时自动检测 `__REDACTED__` 占位符，保留本机已有的敏感值，不会覆盖。

### 4. status — 查看备份状态

```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py status
```

包含完整性校验：自动验证备份文件的 SHA-256 哈希。

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

**只还原 skills 和记忆**：
```bash
python ~/.claude/skills/claude-migrate/scripts/migrate.py restore --conflict backup-existing --only skills memory
```

## 错误处理

| 场景 | 表现 | 处理 |
|------|------|------|
| 未 init 就 `--push` | git push 报错 no remote | 先执行 `init --remote <url>`，再重试 backup |
| 网络断开时 push 失败 | 备份已完成，仅推送失败 | 本地备份不受影响，网络恢复后 `backup --push` 重试 |
| restore 校验失败 | SHA-256 不匹配 | 默认中止；`--force` 可跳过（谨慎使用） |
| 新机器不知道 repo URL | 无法 clone | 旧机器执行 `status` 查看 remote 地址 |
| 还原后脱敏字段为 `__REDACTED__` | 敏感值需手动填写 | 智能合并会保留本机已有值；纯新机器需手动补 token/密码 |

---

## 变更历史

<details>
<summary>v3.0 → v3.4 变更记录（点击展开）</summary>

### v3.4
- 跨平台兼容：移除 `fcntl` 硬依赖，Windows 用 `msvcrt` 条件导入
- symlink 安全回退：Windows 无管理员权限时 fallback 为拷贝
- 权限处理跨平台：Windows 上跳过 Unix 权限记录/还原
- 用户名检测统一：改用 `getpass.getuser()`
- 跨平台路径还原：支持 Linux↔Windows 路径分隔符差异

### v3.3
- skill 备份智能过滤：跳过无 SKILL.md 的非 skill 目录
- description 精简：变更日志移至 body

### v3.2
- .claude.json 白名单过滤：剔除 30+ 个无用运行时字段
- BASE_URL 不再脱敏
- 原子交换回滚完整性：中途失败清理已移入文件
- 跨用户 HOME 路径自动转换
- git clone 锁定 commit SHA
- projects 深度合并还原：allowedTools 取并集

### v3.1
- plans/ 备份（full tier）
- 项目根 CLAUDE.md 发现增强
- smart-merge 权限还原
- stats 独立还原模块
- manifest 精准检测、.gitignore 按行匹配
- 完整性校验失败退出、--version 参数

### v3.0
- 原子备份（staging 目录 → 交换）
- SHA-256 完整性校验
- 智能合并还原（保留本机敏感值）
- 隐私深度清理、路径穿越防护
- 文件权限保留、flock 并发锁
- 选择性恢复（--only）、敏感键白名单

</details>
