#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_REPOS = [
    "pingcap/tidb:master",
    "pingcap/docs:master",
]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def parse_repo_spec(spec: str) -> tuple[str, str, str]:
    main, branch = (spec.split(":", 1) + ["main"])[:2]
    owner, repo = main.split("/", 1)
    return owner.strip(), repo.strip(), branch.strip()


def sync_repo(target_root: Path, owner: str, repo: str, branch: str, depth: int) -> None:
    dest = target_root / f"{owner}__{repo}"
    url = f"https://github.com/{owner}/{repo}.git"

    if (dest / ".git").exists():
        print(f"[update] {owner}/{repo} ({branch}) -> {dest}")
        run(["git", "-C", str(dest), "fetch", "--depth", str(depth), "origin", branch])
        run(["git", "-C", str(dest), "checkout", branch])
        run(["git", "-C", str(dest), "pull", "--ff-only", "origin", branch])
        return

    if dest.exists():
        raise RuntimeError(f"Destination exists but is not a git repo: {dest}")

    print(f"[clone] {owner}/{repo} ({branch}) -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", str(depth), "--branch", branch, url, str(dest)])


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone/pull GitHub repos into data/fake_drive/github for KB sync.")
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Repo spec as owner/name[:branch]. Can be passed multiple times.",
    )
    parser.add_argument(
        "--target",
        default="data/fake_drive/github",
        help="Destination directory (default: data/fake_drive/github).",
    )
    parser.add_argument("--depth", type=int, default=1, help="Shallow clone depth (default: 1).")
    args = parser.parse_args()

    workspace = Path(__file__).resolve().parents[1]
    target_root = (workspace / args.target).resolve()
    repo_specs = args.repo or DEFAULT_REPOS

    for spec in repo_specs:
        owner, repo, branch = parse_repo_spec(spec)
        sync_repo(target_root, owner, repo, branch, args.depth)

    print(f"[done] synced {len(repo_specs)} repos under {target_root}")
    print("[next] run drive sync: curl -X POST http://localhost:8000/admin/sync/drive")


if __name__ == "__main__":
    main()
