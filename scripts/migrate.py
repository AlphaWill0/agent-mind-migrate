#!/usr/bin/env python3
"""
Claude Code 一键迁移工具 v2.0
用法: python migrate.py <backup|restore|status|validate|init> [options]

零外部依赖，仅需 Python 3 标准库 + git CLI。
"""

import argparse
import copy
import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── 常量 ──

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_JSON = Path.home() / ".claude.json"
DEFAULT_REPO = Path.home() / ".claude-backup"
REDACTED = "__REDACTED__"

# 敏感键名模式（不区分大小写）
SENSITIVE_PATTERNS = re.compile(
    r"(TOKEN|SECRET|KEY|PASSWORD|AUTH|CREDENTIAL)", re.IGNORECASE
)
# 额外指定的敏感键（精确匹配）
SENSITIVE_KEYS = {"ANTHROPIC_BASE_URL"}

# 备份时排除的目录（skill 内部）
SKILL_EXCLUDE_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".venv", "venv"}

# ~/.claude.json 中需要脱敏的顶层键
CLAUDE_JSON_SENSITIVE_KEYS = {"userID"}

# ~/.claude.json 中纯粹的运行时状态，不需要备份
CLAUDE_JSON_EPHEMERAL_KEYS = {
    "cachedStatsigGates", "metricsStatusCache", "firstStartTime",
}


# ── 工具函数 ──

def run_git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """运行 git 命令"""
    cmd = ["git"] + args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_ok(msg: str):
    print(f"  [OK] {msg}")


def print_warn(msg: str):
    print(f"  [!!] {msg}")


def print_info(msg: str):
    print(f"  [..] {msg}")


def print_fail(msg: str):
    print(f"  [FAIL] {msg}")


def is_sensitive_key(key: str) -> bool:
    """判断一个 env key 是否敏感"""
    if key in SENSITIVE_KEYS:
        return True
    return bool(SENSITIVE_PATTERNS.search(key))


def sanitize_settings(data: dict) -> tuple[dict, list[str]]:
    """
    对 settings.json 做深拷贝并脱敏。
    返回 (脱敏后的 dict, 被脱敏的字段路径列表)
    """
    sanitized = copy.deepcopy(data)
    redacted_fields = []

    env = sanitized.get("env", {})
    for key, value in env.items():
        if is_sensitive_key(key) and value and value != REDACTED:
            env[key] = REDACTED
            redacted_fields.append(f"settings.json → env.{key}")

    return sanitized, redacted_fields


def sanitize_claude_json(data: dict) -> tuple[dict, list[str]]:
    """
    对 ~/.claude.json 做深拷贝并脱敏。
    - 移除纯运行时字段
    - 脱敏 userID 等敏感字段
    - projects 下的 allowedTools / mcpServers 保留（这是用户积累）
    返回 (脱敏后的 dict, 被脱敏的字段路径列表)
    """
    sanitized = copy.deepcopy(data)
    redacted_fields = []

    # 移除纯运行时状态
    for key in CLAUDE_JSON_EPHEMERAL_KEYS:
        sanitized.pop(key, None)

    # 脱敏敏感字段
    for key in CLAUDE_JSON_SENSITIVE_KEYS:
        if key in sanitized and sanitized[key]:
            sanitized[key] = REDACTED
            redacted_fields.append(f".claude.json → {key}")

    return sanitized, redacted_fields


def get_skill_info(skill_dir: Path) -> dict:
    """获取 skill 的信息：是否 git repo，remote URL 等"""
    info = {"name": skill_dir.name, "type": "local"}

    git_dir = skill_dir / ".git"
    if git_dir.exists():
        # 尝试获取 remote URL
        result = run_git(["remote", "get-url", "origin"], cwd=skill_dir, check=False)
        if result.returncode == 0 and result.stdout.strip():
            info["type"] = "git"
            info["remote"] = result.stdout.strip()

            # 获取当前 branch
            result_branch = run_git(["branch", "--show-current"], cwd=skill_dir, check=False)
            info["branch"] = result_branch.stdout.strip() if result_branch.returncode == 0 else "main"

            # 获取当前 commit SHA
            result_sha = run_git(["rev-parse", "HEAD"], cwd=skill_dir, check=False)
            info["commit"] = result_sha.stdout.strip() if result_sha.returncode == 0 else ""

    return info


def copy_skill_local(src: Path, dst: Path):
    """拷贝本地 skill，排除不需要的目录"""
    if dst.exists():
        shutil.rmtree(dst)

    def ignore_func(directory, contents):
        return {item for item in contents if item in SKILL_EXCLUDE_DIRS}

    shutil.copytree(src, dst, ignore=ignore_func)


def write_gitremote(skill_info: dict, dest_dir: Path):
    """将 git skill 的信息写入 .gitremote 文件"""
    filepath = dest_dir / f"{skill_info['name']}.gitremote"
    content = {
        "name": skill_info["name"],
        "remote": skill_info.get("remote", ""),
        "branch": skill_info.get("branch", "main"),
        "commit": skill_info.get("commit", ""),
    }
    filepath.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")


def copy_dir_if_exists(src: Path, dst: Path, label: str):
    """如果源目录存在则拷贝，返回是否拷贝了"""
    if src.exists() and any(src.iterdir()):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print_ok(f"{label} 已备份")
        return True
    return False


def copy_file_if_exists(src: Path, dst: Path, label: str):
    """如果源文件存在则拷贝，返回是否拷贝了"""
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print_ok(f"{label} 已备份")
        return True
    return False


def find_project_claude_mds() -> list[tuple[Path, str]]:
    """
    发现所有项目根目录中的 CLAUDE.md 文件。
    通过 ~/.claude.json 的 projects 和 githubRepoPaths 找到项目路径。
    返回 [(文件路径, 项目标识), ...]
    """
    results = []

    if not CLAUDE_JSON.exists():
        return results

    try:
        with open(CLAUDE_JSON) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return results

    # 从 projects 键中提取路径
    projects = data.get("projects", {})
    for mangled_path in projects:
        # 反编码：-home-will-clawd → /home/will/clawd
        real_path = "/" + mangled_path.lstrip("-").replace("-", "/")
        # 但 - 在目录名中也是合法的，所以这不完全可靠
        # 更好的方法：直接搜索常见位置
        project_dir = Path(real_path)
        if project_dir.exists():
            for claude_md in [project_dir / "CLAUDE.md", project_dir / ".claude" / "CLAUDE.md"]:
                if claude_md.exists():
                    results.append((claude_md, mangled_path))

    # 从 githubRepoPaths 提取（值可能是 string 或 list[string]）
    repo_paths = data.get("githubRepoPaths", {})
    for repo_name, local_paths in repo_paths.items():
        if isinstance(local_paths, str):
            local_paths = [local_paths]
        if not isinstance(local_paths, list):
            continue
        for local_path in local_paths:
            project_dir = Path(local_path)
            if project_dir.exists():
                for claude_md in [project_dir / "CLAUDE.md", project_dir / ".claude" / "CLAUDE.md"]:
                    if claude_md.exists() and claude_md not in [r[0] for r in results]:
                        results.append((claude_md, repo_name))

    return results


# ── init 命令 ──

def cmd_init(args):
    """初始化备份仓库并配置远程 Git 仓库"""
    repo = Path(args.repo).expanduser()
    remote_url = args.remote

    print_header("初始化备份仓库")

    # 创建并 init
    if not repo.exists():
        repo.mkdir(parents=True)
    if not (repo / ".git").exists():
        run_git(["init"], cwd=repo)
        print_ok(f"已创建 git 仓库: {repo}")
    else:
        print_info(f"git 仓库已存在: {repo}")

    # 配置 remote
    if remote_url:
        # 检查是否已有 remote
        result = run_git(["remote", "get-url", "origin"], cwd=repo, check=False)
        if result.returncode == 0:
            old_url = result.stdout.strip()
            if old_url == remote_url:
                print_ok(f"remote origin 已是: {remote_url}")
            else:
                run_git(["remote", "set-url", "origin", remote_url], cwd=repo)
                print_ok(f"已更新 remote origin: {old_url} → {remote_url}")
        else:
            run_git(["remote", "add", "origin", remote_url], cwd=repo)
            print_ok(f"已添加 remote origin: {remote_url}")

        # 配置 Git 用户名（如果指定了）
        if args.git_user:
            run_git(["config", "user.name", args.git_user], cwd=repo)
            print_ok(f"已设置 git user.name: {args.git_user}")
        if args.git_email:
            run_git(["config", "user.email", args.git_email], cwd=repo)
            print_ok(f"已设置 git user.email: {args.git_email}")

        # 写 .gitignore
        gitignore = repo / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# 不追踪临时文件\n*.pre-restore\n*.tmp\n")
            print_ok("已创建 .gitignore")

        print()
        print_info("初始化完成。现在可以运行:")
        print_info(f"  python {__file__} backup --push")
    else:
        print()
        print_info("仓库已创建（本地模式）。如需配置远程仓库:")
        print_info(f"  python {__file__} init --remote <git-url>")

    print()


# ── backup 命令 ──

def cmd_backup(args):
    repo = Path(args.repo).expanduser()
    tier = args.tier
    message = args.message
    push = args.push

    print_header("Claude Code 备份")
    print_info(f"备份层级: {tier}")
    print_info(f"备份目标: {repo}")

    # 1. 初始化 git repo（如果不存在）
    if not repo.exists():
        repo.mkdir(parents=True)
        run_git(["init"], cwd=repo)
        print_ok(f"已创建备份仓库: {repo}")
    elif not (repo / ".git").exists():
        run_git(["init"], cwd=repo)
        print_ok(f"已初始化 git: {repo}")

    # 2. 清理旧的备份内容（保留 .git 和 .gitignore）
    for item in repo.iterdir():
        if item.name in (".git", ".gitignore"):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    all_sanitized_fields = []

    # ─── 3. ~/.claude.json（主配置文件）───
    if CLAUDE_JSON.exists():
        try:
            with open(CLAUDE_JSON) as f:
                claude_json_data = json.load(f)
            sanitized_data, fields = sanitize_claude_json(claude_json_data)
            all_sanitized_fields.extend(fields)
            with open(repo / "claude.json", "w") as f:
                json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            # 统计关键内容
            projects = sanitized_data.get("projects", {})
            skill_usage = sanitized_data.get("skillUsage", {})
            print_ok(f".claude.json 已备份（{len(projects)} 个项目配置, {len(skill_usage)} 条 skill 使用记录）")
            if fields:
                print_info(f"  脱敏: {', '.join(fields)}")
        except (json.JSONDecodeError, IOError) as e:
            print_warn(f".claude.json 读取失败: {e}")
    else:
        print_info("无 ~/.claude.json，跳过")

    # ─── 4. settings.json（脱敏）───
    settings_src = CLAUDE_HOME / "settings.json"
    if settings_src.exists():
        with open(settings_src) as f:
            settings_data = json.load(f)
        sanitized_data, fields = sanitize_settings(settings_data)
        all_sanitized_fields.extend(fields)
        with open(repo / "settings.json", "w") as f:
            json.dump(sanitized_data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print_ok(f"settings.json 已备份" + (f"（脱敏: {', '.join(fields)}）" if fields else ""))
    else:
        print_warn("settings.json 不存在，跳过")

    # ─── 5. 全局 CLAUDE.md ───
    global_memory = CLAUDE_HOME / "CLAUDE.md"
    if global_memory.exists():
        shutil.copy2(global_memory, repo / "CLAUDE.md")
        print_ok("CLAUDE.md（全局 memory）已备份")
    else:
        print_info("无全局 CLAUDE.md，跳过")

    # ─── 6. rules/ ───
    rules_src = CLAUDE_HOME / "rules"
    copy_dir_if_exists(rules_src, repo / "rules", "rules/（用户规则）")

    # ─── 7. agents/ ───
    agents_src = CLAUDE_HOME / "agents"
    copy_dir_if_exists(agents_src, repo / "agents", "agents/（自定义 agents）")

    # ─── 8. commands/ ───
    commands_src = CLAUDE_HOME / "commands"
    copy_dir_if_exists(commands_src, repo / "commands", "commands/（自定义命令）")

    # ─── 9. scheduled_tasks.json ───
    scheduled_src = CLAUDE_HOME / "scheduled_tasks.json"
    copy_file_if_exists(scheduled_src, repo / "scheduled_tasks.json", "scheduled_tasks.json（定时任务）")

    # ─── 10. Skills ───
    skills_src = CLAUDE_HOME / "skills"
    skills_dst = repo / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    skills_manifest = []

    if skills_src.exists():
        for skill_dir in sorted(skills_src.iterdir()):
            if not skill_dir.is_dir():
                continue

            info = get_skill_info(skill_dir)
            skills_manifest.append(info)

            if info["type"] == "git":
                write_gitremote(info, skills_dst)
                print_ok(f"skill [{info['name']}] → .gitremote（{info['remote']}）")
            else:
                copy_skill_local(skill_dir, skills_dst / info["name"])
                print_ok(f"skill [{info['name']}] → 完整拷贝")
    else:
        print_warn("skills/ 目录不存在")

    # ─── 11. 项目级 CLAUDE.md（~/.claude/projects/ 内）───
    projects_src = CLAUDE_HOME / "projects"
    projects_dst = repo / "projects"
    project_memories_count = 0

    if projects_src.exists():
        for project_dir in projects_src.iterdir():
            if not project_dir.is_dir():
                continue
            for memory_file in [project_dir / "CLAUDE.md", project_dir / "memory" / "CLAUDE.md"]:
                if memory_file.exists():
                    dst_dir = projects_dst / project_dir.name
                    dst_dir.mkdir(parents=True, exist_ok=True)
                    rel = memory_file.relative_to(project_dir)
                    dst_file = dst_dir / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(memory_file, dst_file)
                    project_memories_count += 1

    # ─── 12. 项目根目录的 CLAUDE.md ───
    project_root_mds = find_project_claude_mds()
    for claude_md_path, project_id in project_root_mds:
        # 用项目标识作为子目录名
        safe_id = project_id.replace("/", "-").replace("\\", "-").strip("-")
        dst_dir = repo / "project-root-memories" / safe_id
        dst_dir.mkdir(parents=True, exist_ok=True)

        # 保存 CLAUDE.md 和其来源路径
        shutil.copy2(claude_md_path, dst_dir / "CLAUDE.md")
        (dst_dir / ".source_path").write_text(str(claude_md_path) + "\n")
        project_memories_count += 1

    if project_memories_count > 0:
        print_ok(f"项目级 memory: {project_memories_count} 个已备份")
    else:
        print_info("无项目级 CLAUDE.md")

    # ─── 13. full tier 额外内容 ───
    if tier == "full":
        # history.jsonl
        copy_file_if_exists(CLAUDE_HOME / "history.jsonl", repo / "history.jsonl", "history.jsonl（命令历史）")

        # plugins（排除 .git/node_modules）
        plugins_src = CLAUDE_HOME / "plugins"
        if plugins_src.exists():
            plugins_dst = repo / "plugins"
            if plugins_dst.exists():
                shutil.rmtree(plugins_dst)

            def plugins_ignore(directory, contents):
                return {item for item in contents if item in {".git", "node_modules", "__pycache__"}}

            shutil.copytree(plugins_src, plugins_dst, ignore=plugins_ignore)
            print_ok("plugins/ 已备份")

    # ─── 14. 生成 manifest.json ───
    file_count = 0
    for item in repo.rglob("*"):
        if item.is_file() and ".git" not in item.parts:
            file_count += 1

    manifest = {
        "version": "2.0",
        "created_at": datetime.datetime.now().isoformat(),
        "machine": {
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            "home": str(Path.home()),
        },
        "tier": tier,
        "contents": {
            "claude_json": CLAUDE_JSON.exists(),
            "settings_json": (CLAUDE_HOME / "settings.json").exists(),
            "global_memory": (CLAUDE_HOME / "CLAUDE.md").exists(),
            "rules": (CLAUDE_HOME / "rules").exists(),
            "agents": (CLAUDE_HOME / "agents").exists(),
            "commands": (CLAUDE_HOME / "commands").exists(),
            "scheduled_tasks": (CLAUDE_HOME / "scheduled_tasks.json").exists(),
            "skills": len(skills_manifest),
            "project_memories": project_memories_count,
            "project_root_memories": len(project_root_mds),
            "history": tier == "full" and (CLAUDE_HOME / "history.jsonl").exists(),
            "plugins": tier == "full" and (CLAUDE_HOME / "plugins").exists(),
        },
        "skills": skills_manifest,
        "sanitized_fields": all_sanitized_fields,
        "file_count": file_count + 1,  # +1 for manifest itself
    }

    manifest_path = repo / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print_ok("manifest.json 已生成")

    # ─── 15. Git commit ───
    run_git(["add", "-A"], cwd=repo)

    status_result = run_git(["status", "--porcelain"], cwd=repo)
    if not status_result.stdout.strip():
        print_info("无变更，跳过 commit")
    else:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = message or f"Claude Code 备份 ({tier}) - {timestamp}"
        run_git(["commit", "-m", commit_msg], cwd=repo)
        print_ok(f"已提交: {commit_msg}")

    # ─── 16. 可选推送 ───
    if push:
        # 检查是否有 remote
        remote_check = run_git(["remote", "get-url", "origin"], cwd=repo, check=False)
        if remote_check.returncode != 0:
            print_warn("未配置远程仓库，跳过推送")
            print_info(f"请先运行: python {__file__} init --remote <git-url>")
        else:
            # 检查是否有上游分支，没有则设置
            branch_result = run_git(["branch", "--show-current"], cwd=repo, check=False)
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"

            result = run_git(["push", "-u", "origin", branch], cwd=repo, check=False)
            if result.returncode == 0:
                print_ok(f"已推送到 remote ({remote_check.stdout.strip()})")
            else:
                print_warn(f"推送失败: {result.stderr.strip()}")

    # ─── 17. 汇总 ───
    print_header("备份完成")
    print_info(f"备份位置: {repo}")
    print_info(f"文件总数: {manifest['file_count']}")
    print_info(f"Skills: {len(skills_manifest)} 个（git: {sum(1 for s in skills_manifest if s['type']=='git')}, 本地: {sum(1 for s in skills_manifest if s['type']=='local')}）")
    if all_sanitized_fields:
        print_info(f"脱敏字段: {', '.join(all_sanitized_fields)}")

    # 检查是否配置了 remote
    remote_check = run_git(["remote", "get-url", "origin"], cwd=repo, check=False)
    if remote_check.returncode != 0:
        print()
        print_info("提示: 尚未配置远程仓库。如需推送到远程:")
        print_info(f"  python {__file__} init --remote <git-url>")

    print()


# ── restore 命令 ──

def cmd_restore(args):
    repo = Path(args.repo).expanduser()
    dry_run = args.dry_run
    conflict = args.conflict

    print_header("Claude Code 还原" + ("（DRY RUN）" if dry_run else ""))

    if not repo.exists():
        print_fail(f"备份仓库不存在: {repo}")
        print_info("请先将备份仓库 clone 或拷贝到该路径")
        sys.exit(1)

    manifest_path = repo / "manifest.json"
    if not manifest_path.exists():
        print_fail("manifest.json 不存在，这不是一个有效的备份仓库")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    print_info(f"备份版本: v{manifest.get('version', '1.0')}")
    print_info(f"备份时间: {manifest.get('created_at', '未知')}")
    print_info(f"来源机器: {manifest.get('machine', {}).get('hostname', '未知')}")
    print_info(f"备份层级: {manifest.get('tier', '未知')}")
    print_info(f"冲突策略: {conflict}")
    print()

    actions = []  # (action_type, source, destination, description)

    def plan_file(src: Path, dst: Path, desc: str):
        if dst.exists():
            if conflict == "skip":
                actions.append(("skip", src, dst, f"[跳过] {desc}（已存在）"))
            elif conflict == "overwrite":
                actions.append(("overwrite", src, dst, f"[覆盖] {desc}"))
            elif conflict == "backup-existing":
                actions.append(("backup-overwrite", src, dst, f"[备份+覆盖] {desc}"))
        else:
            actions.append(("create", src, dst, f"[新建] {desc}"))

    def plan_dir(src: Path, dst: Path, desc: str):
        """规划整个目录的拷贝"""
        if not src.exists():
            return
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                plan_file(item, dst / rel, f"{desc}/{rel}")

    # 1. claude.json → ~/.claude.json
    claude_json_src = repo / "claude.json"
    if claude_json_src.exists():
        plan_file(claude_json_src, CLAUDE_JSON, ".claude.json（主配置）")

    # 2. settings.json
    settings_src = repo / "settings.json"
    if settings_src.exists():
        plan_file(settings_src, CLAUDE_HOME / "settings.json", "settings.json")

    # 3. 全局 CLAUDE.md
    memory_src = repo / "CLAUDE.md"
    if memory_src.exists():
        plan_file(memory_src, CLAUDE_HOME / "CLAUDE.md", "CLAUDE.md（全局 memory）")

    # 4. rules/
    rules_src = repo / "rules"
    if rules_src.exists():
        plan_dir(rules_src, CLAUDE_HOME / "rules", "rules")

    # 5. agents/
    agents_src = repo / "agents"
    if agents_src.exists():
        plan_dir(agents_src, CLAUDE_HOME / "agents", "agents")

    # 6. commands/
    commands_src = repo / "commands"
    if commands_src.exists():
        plan_dir(commands_src, CLAUDE_HOME / "commands", "commands")

    # 7. scheduled_tasks.json
    sched_src = repo / "scheduled_tasks.json"
    if sched_src.exists():
        plan_file(sched_src, CLAUDE_HOME / "scheduled_tasks.json", "scheduled_tasks.json（定时任务）")

    # 8. Skills
    skills_src = repo / "skills"
    if skills_src.exists():
        for item in sorted(skills_src.iterdir()):
            if item.is_dir():
                plan_dir(item, CLAUDE_HOME / "skills" / item.name, f"skill/{item.name}")
            elif item.suffix == ".gitremote":
                with open(item) as f:
                    gitinfo = json.load(f)
                skill_name = gitinfo["name"]
                dst = CLAUDE_HOME / "skills" / skill_name
                if dst.exists():
                    if conflict == "skip":
                        actions.append(("skip", item, dst, f"[跳过] skill/{skill_name}（git, 已存在）"))
                    elif conflict == "overwrite":
                        actions.append(("git-clone", item, dst, f"[重新 clone] skill/{skill_name} ← {gitinfo['remote']}"))
                    elif conflict == "backup-existing":
                        actions.append(("git-clone-backup", item, dst, f"[备份+clone] skill/{skill_name} ← {gitinfo['remote']}"))
                else:
                    actions.append(("git-clone", item, dst, f"[clone] skill/{skill_name} ← {gitinfo['remote']}"))

    # 9. 项目级 memory（~/.claude/projects/）
    projects_src = repo / "projects"
    if projects_src.exists():
        for project_dir in projects_src.iterdir():
            if project_dir.is_dir():
                plan_dir(project_dir, CLAUDE_HOME / "projects" / project_dir.name, f"project-memory/{project_dir.name}")

    # 10. 项目根目录 CLAUDE.md
    project_root_src = repo / "project-root-memories"
    if project_root_src.exists():
        for project_dir in project_root_src.iterdir():
            if not project_dir.is_dir():
                continue
            source_path_file = project_dir / ".source_path"
            if source_path_file.exists():
                original_path = Path(source_path_file.read_text().strip())
                claude_md = project_dir / "CLAUDE.md"
                if claude_md.exists():
                    plan_file(claude_md, original_path, f"项目 CLAUDE.md → {original_path}")

    # 11. history.jsonl
    history_src = repo / "history.jsonl"
    if history_src.exists():
        plan_file(history_src, CLAUDE_HOME / "history.jsonl", "history.jsonl")

    # 12. plugins
    plugins_src = repo / "plugins"
    if plugins_src.exists():
        plan_dir(plugins_src, CLAUDE_HOME / "plugins", "plugins")

    # 显示计划
    print_header("还原计划")
    if not actions:
        print_info("没有需要还原的内容")
        return

    for action_type, src, dst, desc in actions:
        print(f"  {desc}")

    create_count = sum(1 for a in actions if a[0] == "create")
    overwrite_count = sum(1 for a in actions if a[0] in ("overwrite", "backup-overwrite"))
    skip_count = sum(1 for a in actions if a[0] == "skip")
    clone_count = sum(1 for a in actions if a[0] in ("git-clone", "git-clone-backup"))

    print()
    print_info(f"新建: {create_count}, 覆盖: {overwrite_count}, 跳过: {skip_count}, Git clone: {clone_count}")

    if dry_run:
        print()
        print_warn("这是 DRY RUN，未做任何实际操作")
        print_info("确认无误后，运行不带 --dry-run 的命令来实际执行还原")
        return

    # 实际执行
    print_header("正在执行还原...")

    for action_type, src, dst, desc in actions:
        if action_type == "skip":
            continue

        elif action_type == "create":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        elif action_type == "overwrite":
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        elif action_type == "backup-overwrite":
            backup_path = dst.with_suffix(dst.suffix + ".pre-restore")
            shutil.copy2(dst, backup_path)
            shutil.copy2(src, dst)

        elif action_type == "git-clone":
            with open(src) as f:
                gitinfo = json.load(f)
            if dst.exists():
                shutil.rmtree(dst)
            branch = gitinfo.get("branch", "main")
            result = run_git(["clone", "-b", branch, gitinfo["remote"], str(dst)], check=False)
            if result.returncode != 0:
                print_warn(f"Clone 失败 [{gitinfo['name']}]: {result.stderr.strip()}")
                continue

        elif action_type == "git-clone-backup":
            with open(src) as f:
                gitinfo = json.load(f)
            if dst.exists():
                backup_dir = dst.with_suffix(".pre-restore")
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                dst.rename(backup_dir)
            branch = gitinfo.get("branch", "main")
            result = run_git(["clone", "-b", branch, gitinfo["remote"], str(dst)], check=False)
            if result.returncode != 0:
                print_warn(f"Clone 失败 [{gitinfo['name']}]: {result.stderr.strip()}")
                continue

        print_ok(desc.split("] ", 1)[-1] if "] " in desc else desc)

    # 检查脱敏字段
    sanitized = manifest.get("sanitized_fields", [])
    if sanitized:
        print_header("需要手动填写的脱敏字段")
        print_warn("以下字段在备份时被自动脱敏，请手动填写：")
        for field in sanitized:
            print(f"    - {field}")
        print()

    print_header("还原完成")
    print_info("建议运行 validate 命令检查还原结果：")
    print_info(f"  python {__file__} validate")
    print()


# ── status 命令 ──

def cmd_status(args):
    repo = Path(args.repo).expanduser()

    print_header("Claude Code 备份状态")

    if not repo.exists() or not (repo / ".git").exists():
        print_warn(f"备份仓库不存在或不是 git 仓库: {repo}")
        print_info("运行 backup 命令创建首次备份")
        return

    # 读取 manifest
    manifest_path = repo / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        print_info(f"备份版本: v{manifest.get('version', '1.0')}")
        print_info(f"最近备份时间: {manifest.get('created_at', '未知')}")
        print_info(f"备份层级: {manifest.get('tier', '未知')}")
        print_info(f"来源机器: {manifest.get('machine', {}).get('hostname', '未知')}")
        print_info(f"文件总数: {manifest.get('file_count', '未知')}")

        # 内容清单
        contents = manifest.get("contents", {})
        if contents:
            items = []
            if contents.get("claude_json"): items.append(".claude.json")
            if contents.get("settings_json"): items.append("settings.json")
            if contents.get("global_memory"): items.append("CLAUDE.md")
            if contents.get("rules"): items.append("rules/")
            if contents.get("agents"): items.append("agents/")
            if contents.get("commands"): items.append("commands/")
            if contents.get("scheduled_tasks"): items.append("scheduled_tasks.json")
            if contents.get("history"): items.append("history.jsonl")
            if contents.get("plugins"): items.append("plugins/")
            print_info(f"包含: {', '.join(items)}")

        skills = manifest.get("skills", [])
        git_skills = [s for s in skills if s["type"] == "git"]
        local_skills = [s for s in skills if s["type"] == "local"]
        print_info(f"Skills: {len(skills)} 个（git: {len(git_skills)}, 本地: {len(local_skills)}）")

        pm = contents.get("project_memories", 0)
        prm = contents.get("project_root_memories", 0)
        if pm or prm:
            print_info(f"项目 memory: {pm} 个（projects/）+ {prm} 个（项目根目录）")

        if manifest.get("sanitized_fields"):
            print_info(f"脱敏字段: {', '.join(manifest['sanitized_fields'])}")
    else:
        print_warn("manifest.json 不存在")

    # Remote 状态
    remote_result = run_git(["remote", "get-url", "origin"], cwd=repo, check=False)
    if remote_result.returncode == 0:
        print_info(f"远程仓库: {remote_result.stdout.strip()}")
    else:
        print_info("远程仓库: 未配置")

    # Git 日志
    print_header("备份历史（最近 10 次）")
    result = run_git(
        ["log", "--oneline", "--format=%h  %ci  %s", "-10"],
        cwd=repo, check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        for line in result.stdout.strip().split("\n"):
            print(f"  {line}")
    else:
        print_info("暂无备份记录")

    # 差异检测
    print_header("当前配置 vs 最近备份")

    # Skills 差异
    live_skills = set()
    skills_dir = CLAUDE_HOME / "skills"
    if skills_dir.exists():
        for d in skills_dir.iterdir():
            if d.is_dir():
                live_skills.add(d.name)

    backed_skills = set()
    backup_skills_dir = repo / "skills"
    if backup_skills_dir.exists():
        for item in backup_skills_dir.iterdir():
            if item.is_dir():
                backed_skills.add(item.name)
            elif item.suffix == ".gitremote":
                backed_skills.add(item.stem)

    new_skills = live_skills - backed_skills
    removed_skills = backed_skills - live_skills

    if new_skills:
        print_warn(f"新增未备份的 skills: {', '.join(sorted(new_skills))}")
    if removed_skills:
        print_warn(f"已备份但本地已删除: {', '.join(sorted(removed_skills))}")
    if not new_skills and not removed_skills:
        print_ok("Skills 列表与备份一致")

    # settings.json 差异
    settings_live = CLAUDE_HOME / "settings.json"
    settings_backup = repo / "settings.json"
    if settings_live.exists() and settings_backup.exists():
        with open(settings_live) as f:
            live_data = json.load(f)
        with open(settings_backup) as f:
            backup_data = json.load(f)

        live_compare = copy.deepcopy(live_data)
        for field in manifest.get("sanitized_fields", []):
            if "settings.json" not in field:
                continue
            key_path = field.split("→")[-1].strip() if "→" in field else field
            parts = key_path.split(".")
            obj = live_compare
            for part in parts[:-1]:
                obj = obj.get(part, {})
            if isinstance(obj, dict) and parts[-1] in obj:
                obj[parts[-1]] = REDACTED

        if live_compare == backup_data:
            print_ok("settings.json 与备份一致（忽略脱敏字段）")
        else:
            print_warn("settings.json 已有变更（建议重新备份）")

    # 全局 CLAUDE.md
    global_memory = CLAUDE_HOME / "CLAUDE.md"
    backup_memory = repo / "CLAUDE.md"
    if global_memory.exists() and not backup_memory.exists():
        print_warn("全局 CLAUDE.md 存在但未备份")
    elif not global_memory.exists() and backup_memory.exists():
        print_info("备份中有全局 CLAUDE.md，但本地已删除")
    elif global_memory.exists() and backup_memory.exists():
        if global_memory.read_text() == backup_memory.read_text():
            print_ok("全局 CLAUDE.md 与备份一致")
        else:
            print_warn("全局 CLAUDE.md 已有变更（建议重新备份）")

    # .claude.json 差异
    if CLAUDE_JSON.exists() and (repo / "claude.json").exists():
        print_ok(".claude.json 已备份")
    elif CLAUDE_JSON.exists():
        print_warn(".claude.json 存在但未备份（可能是 v1 备份）")

    print()


# ── validate 命令 ──

def cmd_validate(args):
    print_header("Claude Code 安装验证")

    issues = 0

    # 1. ~/.claude.json
    if CLAUDE_JSON.exists():
        try:
            with open(CLAUDE_JSON) as f:
                data = json.load(f)
            print_ok(f".claude.json 有效（{len(data)} 个顶层键）")

            # 检查脱敏占位符
            if data.get("userID") == REDACTED:
                print_warn(".claude.json 中 userID 为占位符（正常，会自动重新生成）")
        except json.JSONDecodeError as e:
            print_fail(f".claude.json JSON 解析失败: {e}")
            issues += 1
    else:
        print_info("无 ~/.claude.json（首次启动时会自动创建）")

    # 2. settings.json
    settings_path = CLAUDE_HOME / "settings.json"
    if settings_path.exists():
        try:
            with open(settings_path) as f:
                data = json.load(f)
            print_ok("settings.json 是有效 JSON")

            env = data.get("env", {})
            redacted = [k for k, v in env.items() if v == REDACTED]
            if redacted:
                print_fail(f"settings.json 中残留 {REDACTED} 占位符: {', '.join(redacted)}")
                issues += 1
            else:
                print_ok("settings.json 无残留占位符")
        except json.JSONDecodeError as e:
            print_fail(f"settings.json JSON 解析失败: {e}")
            issues += 1
    else:
        print_warn("settings.json 不存在")
        issues += 1

    # 3. Skills 完整性
    skills_dir = CLAUDE_HOME / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                print_ok(f"skill [{skill_dir.name}] SKILL.md ✓")
            else:
                found = list(skill_dir.rglob("SKILL.md"))
                if found:
                    print_ok(f"skill [{skill_dir.name}] SKILL.md ✓（{found[0].relative_to(skill_dir)}）")
                else:
                    print_warn(f"skill [{skill_dir.name}] 缺少 SKILL.md")
                    issues += 1

            # Git-based skills
            git_dir = skill_dir / ".git"
            if git_dir.exists():
                result = run_git(["remote", "get-url", "origin"], cwd=skill_dir, check=False)
                if result.returncode == 0:
                    remote = result.stdout.strip()
                    if remote.startswith("http") or remote.startswith("git@"):
                        print_ok(f"  └ git remote: {remote}")
                    else:
                        print_warn(f"  └ git remote 格式异常: {remote}")
                        issues += 1
    else:
        print_warn("skills/ 目录不存在")

    # 4. 其他配置目录
    for name, label in [("rules", "用户规则"), ("agents", "自定义 agents"), ("commands", "自定义命令")]:
        path = CLAUDE_HOME / name
        if path.exists():
            count = sum(1 for f in path.rglob("*.md"))
            print_ok(f"{name}/ 存在（{count} 个 .md 文件）")

    # 5. 全局 CLAUDE.md
    global_memory = CLAUDE_HOME / "CLAUDE.md"
    if global_memory.exists():
        print_ok("全局 CLAUDE.md 存在")
    else:
        print_info("无全局 CLAUDE.md（可通过 /memory 创建）")

    # 6. scheduled_tasks.json
    sched = CLAUDE_HOME / "scheduled_tasks.json"
    if sched.exists():
        try:
            with open(sched) as f:
                json.load(f)
            print_ok("scheduled_tasks.json 有效")
        except json.JSONDecodeError:
            print_fail("scheduled_tasks.json 无效 JSON")
            issues += 1

    # 汇总
    print_header("验证结果")
    if issues == 0:
        print_ok("全部检查通过，环境健康")
    else:
        print_fail(f"发现 {issues} 个问题，请检查上方输出")

    print()
    return issues


# ── CLI 入口 ──

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code 一键迁移工具 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s init --remote git@github.com:user/backup.git   # 配置远程仓库
  %(prog)s backup                                          # 备份到 ~/.claude-backup
  %(prog)s backup --push                                   # 备份并推送到远程
  %(prog)s backup --tier full --push -m "完整备份"          # 完整备份并推送
  %(prog)s restore --dry-run                               # 预览还原
  %(prog)s restore --conflict backup-existing              # 实际还原
  %(prog)s status                                          # 查看备份状态
  %(prog)s validate                                        # 健康检查
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="初始化备份仓库并配置远程 Git")
    p_init.add_argument("--repo", default=str(DEFAULT_REPO), help="备份仓库路径（默认: ~/.claude-backup）")
    p_init.add_argument("--remote", help="远程 Git 仓库 URL")
    p_init.add_argument("--git-user", help="Git 用户名")
    p_init.add_argument("--git-email", help="Git 邮箱")

    # backup
    p_backup = subparsers.add_parser("backup", help="备份当前 Claude Code 配置")
    p_backup.add_argument("--repo", default=str(DEFAULT_REPO), help="备份仓库路径（默认: ~/.claude-backup）")
    p_backup.add_argument("--tier", choices=["essential", "full"], default="essential", help="备份层级（默认: essential）")
    p_backup.add_argument("--message", "-m", help="自定义 commit message")
    p_backup.add_argument("--push", action="store_true", help="备份后推送到 remote")

    # restore
    p_restore = subparsers.add_parser("restore", help="从备份还原 Claude Code 配置")
    p_restore.add_argument("--repo", default=str(DEFAULT_REPO), help="备份仓库路径（默认: ~/.claude-backup）")
    p_restore.add_argument("--dry-run", action="store_true", default=False, help="只预览，不实际操作")
    p_restore.add_argument("--conflict", choices=["overwrite", "skip", "backup-existing"], default="skip", help="冲突处理策略（默认: skip）")

    # status
    p_status = subparsers.add_parser("status", help="查看备份状态和差异")
    p_status.add_argument("--repo", default=str(DEFAULT_REPO), help="备份仓库路径（默认: ~/.claude-backup）")

    # validate
    p_validate = subparsers.add_parser("validate", help="验证当前安装的健康状态")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "backup":
        cmd_backup(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "validate":
        sys.exit(cmd_validate(args))


if __name__ == "__main__":
    main()
