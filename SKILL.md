---
name: agent-mind-migrate
description: |
  多 Agent 统一备份/迁移工具。一键备份 Claude Code、OpenClaw、Hermes 等 AI Agent 的全部配置和积累到 Git 仓库，支持跨机器一键还原。自动发现已安装的 Agent，按 Agent 独立存储。
  触发词：备份、迁移、backup、restore、migrate、搬家、换机器、一键迁移、导出配置、导入配置、备份我的配置、帮我打包、迁移到新机器、备份你的记忆技能、保存你的记忆、备份记忆、agent备份、多agent迁移。
  即使用户只是说"我要换机器了"或"帮我把这些东西保存下来"或"备份一下"，只要上下文暗示需要保存/迁移 AI Agent 的状态，都应该触发。
  不要用于普通的文件备份或 git 操作。
metadata:
  category: custom
  author: AlphaWill
  version: "4.0"
---

# Agent Mind Migrate v4.0 — 多 Agent 统一迁移

一条命令备份你所有 AI Agent 的积累，一条命令还原到新机器。

**脚本路径**：`~/.claude/skills/agent-mind-migrate/scripts/migrate.py`（下文简写为 `migrate.py`）

---

## 命令速查

| 命令 | 用途 | 示例 |
|------|------|------|
| `backup` | 备份所有已安装 Agent | `migrate.py backup --push` |
| `restore` | 从备份还原 | `migrate.py restore --dry-run` |
| `init` | 初始化远程仓库 | `migrate.py init --remote <url>` |
| `status` | 查看备份状态 | `migrate.py status` |
| `validate` | 健康检查 | `migrate.py validate` |

---

## backup — 备份

```bash
python migrate.py backup [--tier essential|full] [--agents claude-code,openclaw,hermes] [--push]
```

- 自动发现本机已安装的 Agent，全部备份到 `~/.claude-backup/`
- **备份前先告知用户检测到哪些 Agent、上次备份时间，确认后再执行**
- `--tier essential`（默认）：核心配置。`--tier full`：含历史和插件（**换机器推荐**）
- `--agents`：只备份指定 Agent。不传则自动发现并备份所有
- `--push`：推送到远程仓库（**网络外发操作，执行前告知用户**）。如果用户没明确说要推送，默认只做本地备份，问用户是否要推送
- 自动脱敏 token/密码 → `__REDACTED__`
- 原子写入 + SHA-256 完整性校验
- git skill（`.gitremote` 文件）只存 URL + commit SHA，不拷贝整个仓库

## restore — 还原

> **⚠️ 还原前必须先 dry-run 预览。** 跳过 dry-run 直接执行会提示警告。

### 还原三步走

```bash
# Step 1: 预览（必须先跑，确认要还原的文件列表）
python migrate.py restore --dry-run

# Step 2: 执行还原（用户确认 dry-run 输出后再运行）
python migrate.py restore --conflict backup-existing \
  [--agents claude-code,openclaw] [--only skills memory config]

# Step 3: 验证 + 补全脱敏字段
python migrate.py validate
# 检查输出中的 __REDACTED__ 字段，手动填入真实值
```

### 参数说明

- `--conflict`：`backup-existing`（**推荐**，备份旧文件后覆盖） / `overwrite`（直接覆盖） / `skip`（跳过已有）
- `--agents`：只还原指定 Agent
- `--only`：按模块选择还原范围
  - 核心：`config` `memory` `skills` `rules`
  - 扩展：`agents` `commands` `scheduled_tasks` `stats` `project_memories`
  - Full 层级：`plans` `history` `plugins`
- `--force`：完整性校验失败时强制继续（谨慎使用）
- 智能合并：`__REDACTED__` 占位符保留本机已有敏感值，不会覆盖真实密钥

## init — 初始化远程仓库

```bash
python migrate.py init --remote <git-url> [--git-user "名字"] [--git-email "邮箱"]
```

首次使用时运行。之后 `backup --push` 即可直接推送。

## status / validate

```bash
python migrate.py status     # 每个 Agent 的备份时间、文件数、完整性
python migrate.py validate   # 本机环境健康检查
```

`status` 输出示例：
```
Claude Code  ✅ 上次备份: 2026-04-16 19:10  文件: 42  完整性: OK
OpenClaw     ✅ 上次备份: 2026-04-16 19:10  文件: 8   完整性: OK
Hermes       ⚠️ 未检测到（~/.hermes/ 不存在）
```

---

## 支持的 Agent

| Agent | 配置目录 | 备份内容 | 脱敏 |
|-------|---------|---------|------|
| **Claude Code** | `~/.claude/` | 主配置、settings、memory、skills、rules、agents、commands、定时任务、统计、项目记忆 | token/密码 → `__REDACTED__` |
| **OpenClaw** | `~/.openclaw/` | 主配置、bot配置、记忆(sqlite)、定时任务、插件、设备 | auth 字段 → `__REDACTED__` |
| **Hermes** | `~/.hermes/` | 配置、身份(SOUL.md)、记忆、技能、定时任务 | 敏感文件直接排除 |

<details>
<summary>各 Agent 备份详情（点击展开）</summary>

### Claude Code

| 内容 | 文件/路径 | essential | full |
|------|-----------|:---------:|:----:|
| 主配置 | `~/.claude.json` | Y | Y |
| Settings | `~/.claude/settings.json` | Y | Y |
| 全局 Memory | `~/.claude/CLAUDE.md` | Y | Y |
| Skills | `~/.claude/skills/` | Y | Y |
| Rules | `~/.claude/rules/` | Y | Y |
| Agents | `~/.claude/agents/` | Y | Y |
| Commands | `~/.claude/commands/` | Y | Y |
| 定时任务 | `~/.claude/scheduled_tasks.json` | Y | Y |
| 使用统计 | `~/.claude/stats-cache.json` | Y | Y |
| 项目级 Memory | `~/.claude/projects/*/CLAUDE.md` | Y | Y |
| 命令历史 | `~/.claude/history.jsonl` | - | Y |
| 规划方案 | `~/.claude/plans/*.md` | - | Y |
| Plugins | `~/.claude/plugins/` | - | Y |

### OpenClaw

| 内容 | 文件/路径 | 排除 |
|------|-----------|------|
| 主配置 | `openclaw.json`（auth 脱敏） | `credentials/` |
| Bot 配置 | `clawdbot.json` | `*.bak*` |
| 记忆 | `memory/main.sqlite` | `logs/` |
| 定时任务 | `cron/jobs.json` | `tasks/` |
| 插件 | `extensions/`（跳过 node_modules） | |
| 设备 | `devices/` | |

### Hermes

| 内容 | 文件/路径 | 排除 |
|------|-----------|------|
| 配置 | `config.yaml` | `.env` |
| 身份 | `SOUL.md` | `auth.json` |
| 记忆 | `memories/`（MEMORY.md, USER.md） | `logs/` |
| 技能 | `skills/` | `sessions/` |
| 定时任务 | `cron/` | `browser_recordings/` |

</details>

---

## 备份目录结构

每个 Agent 独立一个文件夹，互不干扰：

```
~/.claude-backup/
├── manifest.json           # agents: ["claude-code", "openclaw", "hermes"]
├── claude-code/            # Claude Code 的所有备份
│   ├── claude.json
│   ├── settings.json
│   ├── skills/
│   └── ...
├── openclaw/               # OpenClaw 的备份
│   ├── openclaw.json
│   ├── memory/
│   └── ...
└── hermes/                 # Hermes 的备份
    ├── config.yaml
    ├── memories/
    └── ...
```

向后兼容：检测到 v3.x 旧格式（无 Agent 子目录）时，自动按 Claude Code 处理。

---

## 使用场景

> **快速决策**：根据用户意图选择对应动作，不需要用户了解具体命令。

### 「备份一下」/ 「backup」

1. 运行 `migrate.py status` 了解当前状态
2. 告知用户检测到哪些 Agent、上次备份时间
3. 用户确认后运行 `migrate.py backup --push`
4. 汇报结果（备份了几个 Agent、几个文件、是否推送成功）

### 「我要换机器了」/ 「迁移」

引导用户在**旧机器**执行完整备份，然后给出新机器的还原步骤：

```
旧机器：
  1. backup --tier full --push

新机器：
  2. git clone <backup-repo-url> ~/.claude-backup
  3. git clone https://github.com/AlphaWill0/agent-mind-migrate.git ~/.claude/skills/agent-mind-migrate
  4. python migrate.py restore --dry-run          ← 预览还原内容
  5. python migrate.py restore --conflict backup-existing
  6. python migrate.py validate                   ← 检查 + 补填 __REDACTED__
```

### 「只还原某个 Agent / 某些模块」

根据用户意图拼接参数：
- 指定 Agent → `--agents openclaw`
- 指定模块 → `--only skills memory`
- 两者可组合 → `--agents claude-code --only skills`

始终先 `--dry-run` 预览，确认后再执行。

---

## 错误处理

| 场景 | 处理 |
|------|------|
| Agent 未安装（目录不存在） | 自动跳过，status 中标注「未检测到」 |
| 未 init 就 `--push` | 提示先执行 `init --remote <url>` |
| 网络断开时 push 失败 | 本地备份不受影响，网络恢复后重试 |
| restore 校验失败（SHA-256 不匹配） | 默认中止并提示重新 clone；`--force` 可跳过 |
| 旧格式备份（v3.x） | 自动识别为 Claude Code，正常还原 |
| `__REDACTED__` 占位符 | 智能合并保留本机已有值；纯新机器需手动补 |
| 备份仓库不存在 | 提示先 `git clone` 或 `init` |
| OpenClaw sqlite 被其他进程锁定 | 等待或提示关闭 OpenClaw 后重试 |
| 备份仓库磁盘空间不足 | 中止并提示可用空间和预计需要大小 |

---

<details>
<summary>变更历史（点击展开）</summary>

### v4.0
- 多 Agent 支持：Claude Code + OpenClaw + Hermes
- 备份目录按 Agent 独立存储
- 新增 `--agents` 参数按 Agent 筛选
- AgentPlugin 架构，可扩展更多 Agent
- 向后兼容 v3.x 备份格式
- 重命名 claude-migrate → agent-mind-migrate

### v3.4
- 跨平台兼容（Windows / macOS / Linux）
- symlink 安全回退、权限处理跨平台

### v3.3
- skill 备份智能过滤、description 精简

### v3.2
- .claude.json 白名单过滤、原子交换回滚
- 跨用户 HOME 路径转换、git clone 锁定 SHA

### v3.1
- plans/ 备份、smart-merge 权限还原
- manifest 精准检测、完整性校验

### v3.0
- 原子备份、SHA-256 校验、智能合并还原
- 隐私深度清理、选择性恢复

</details>
