import os
import sys
import time
import subprocess
from pathlib import Path

REPO_PATH = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
MESSAGE_FILE = Path(os.environ.get("AUTOPUSH_MSG_FILE", REPO_PATH / ".autopush_message.txt"))
DEBOUNCE_SECONDS = float(os.environ.get("AUTOPUSH_DEBOUNCE", "3"))
IGNORE_DIRS = {".git", "node_modules", ".venv", "venv"}


def is_git_repo(path: Path) -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def current_branch(path: Path) -> str:
    res = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, capture_output=True, text=True)
    return (res.stdout or "main").strip() or "main"


def has_changes(path: Path) -> bool:
    res = subprocess.run(["git", "status", "--porcelain"], cwd=path, capture_output=True, text=True)
    return bool(res.stdout.strip())


def read_message_file() -> str:
    try:
        if MESSAGE_FILE.exists() and MESSAGE_FILE.is_file():
            content = MESSAGE_FILE.read_text(encoding="utf-8").strip()
            return content
    except Exception:
        pass
    return ""


def clear_message_file():
    try:
        if MESSAGE_FILE.exists():
            # one-shot message – clear after use
            MESSAGE_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass


def autopush(path: Path):
    if not has_changes(path):
        return
    branch = current_branch(path)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Priority: one-shot message file > session env var
    user_note = read_message_file()
    if not user_note:
        user_note = os.environ.get("AUTOPUSH_NOTE", "").strip()
    try:
        subprocess.run(["git", "add", "-A"], cwd=path, check=True)
        # Build informative commit message from staged changes
        files_res = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=path, capture_output=True, text=True)
        stat_res = subprocess.run(["git", "diff", "--cached", "--stat"], cwd=path, capture_output=True, text=True)
        files_list = "\n".join(f"- {line}" for line in files_res.stdout.strip().splitlines() if line)
        stat_block = stat_res.stdout.strip()
        lines = []
        lines.append(f"autopush: {stamp}")
        if user_note:
            lines.append("")
            lines.append(user_note)
        if files_list:
            lines.append("")
            lines.append("Changed files:")
            lines.append(files_list)
        if stat_block:
            lines.append("")
            lines.append("Diffstat:")
            lines.append(stat_block)
        commit_msg = "\n".join(lines)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=path, check=True)
        subprocess.run(["git", "push", "origin", branch], cwd=path, check=True)
        print(f"✅ autopushed at {stamp} on {branch}")
        if user_note:
            clear_message_file()
    except subprocess.CalledProcessError as e:
        print(f"⚠️ autopush failed: {e}")


def walk_mtimes(path: Path) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            try:
                p = Path(root) / f
                total ^= int(p.stat().st_mtime_ns)  # cheap rolling hash
            except Exception:
                pass
    return total


def main():
    print(f"🚀 auto_git_push watching: {REPO_PATH}")
    if not is_git_repo(REPO_PATH):
        print("❌ Not a git repository.")
        sys.exit(1)
    last_hash = walk_mtimes(REPO_PATH)
    last_change = time.time()

    while True:
        time.sleep(0.5)
        h = walk_mtimes(REPO_PATH)
        if h != last_hash:
            last_hash = h
            last_change = time.time()
        # debounce
        if time.time() - last_change >= DEBOUNCE_SECONDS:
            autopush(REPO_PATH)
            last_change = float('inf')  # wait for next change


if __name__ == "__main__":
    main()


