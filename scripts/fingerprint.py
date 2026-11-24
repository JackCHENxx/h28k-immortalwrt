#!/usr/bin/env python3
"""生成 H28K 构建指纹：上游 tag + feeds 锁定 commit + 本仓库 commit + 配置。

用法:
  python3 scripts/fingerprint.py --tag v25.12.2 --variant default \
      --config config/h28k.config [--info build-info-tail.txt] [--json out.json]

stdout 只输出一个 64 位十六进制指纹，便于 workflow / build.sh 直接捕获。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
UPSTREAM_RAW = "https://raw.githubusercontent.com/immortalwrt/immortalwrt/{tag}/feeds.conf.default"
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def fail(msg: str) -> None:
    print(f"[fingerprint] {msg}", file=sys.stderr)
    raise SystemExit(2)


def repo_commit() -> str:
    proc = subprocess.run(
        ["git", "-C", str(KIT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        fail("取不到本仓库 commit（不在 git 工作树里？）")
    return proc.stdout.strip()


def fetch_feeds_conf(tag: str) -> str:
    url = UPSTREAM_RAW.format(tag=tag)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - 网络失败时给出明确错误
        fail(f"无法获取 {url}: {exc}")


def resolve_ref(url: str, ref: str) -> str:
    """feed 指向分支/tag 时解析成 commit；指向 40 位 commit 时直接使用。"""
    if HEX40.fullmatch(ref):
        return ref
    try:
        proc = subprocess.run(
            ["git", "ls-remote", url, ref],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        fail(f"解析 feed {url} {ref} 失败: {exc}")
    if proc.returncode != 0:
        fail(f"git ls-remote 失败 {url} {ref}: {proc.stderr.strip()}")
    first = proc.stdout.splitlines()[0] if proc.stdout.splitlines() else ""
    sha = first.split()[0] if first else ""
    if not HEX40.fullmatch(sha):
        fail(f"feed {url} 的 ref {ref} 解析不到 commit")
    return sha


def parse_feeds(text: str) -> dict[str, str]:
    feeds: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or not line.startswith("src-git"):
            continue
        parts = line.split()
        if len(parts) < 3:
            fail(f"feeds.conf.default 行格式不正确: {raw}")
        name, spec = parts[1], parts[2]
        if "^" in spec:
            url, ref = spec.rsplit("^", 1)
        else:
            url, ref = spec, "HEAD"
        feeds[name] = resolve_ref(url, ref)
    if not feeds:
        fail("feeds.conf.default 里没有解析到任何 src-git feed")
    return feeds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--variant", required=True, choices=["default", "experience"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--info", help="把 fingerprint/repo_commit/feeds 追加写到该文件")
    ap.add_argument("--json", help="把完整指纹材料写到该 JSON 文件")
    args = ap.parse_args()

    config = Path(args.config)
    if not config.is_absolute():
        config = KIT / config
    if not config.is_file():
        fail(f"配置种子不存在: {config}")

    feeds_text = fetch_feeds_conf(args.tag)
    feeds = parse_feeds(feeds_text)
    feeds_conf_sha = hashlib.sha256(feeds_text.encode("utf-8")).hexdigest()
    config_sha = hashlib.sha256(config.read_bytes()).hexdigest()
    head = repo_commit()

    material = {
        "tag": args.tag,
        "variant": args.variant,
        "repo_commit": head,
        "config_sha256": config_sha,
        "feeds_conf_sha256": feeds_conf_sha,
        "feeds": feeds,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    if args.json:
        Path(args.json).write_text(
            json.dumps(material, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if args.info:
        feed_line = " ".join(f"{name}={sha}" for name, sha in sorted(feeds.items()))
        Path(args.info).write_text(
            "\n".join(
                [
                    f"fingerprint: {fingerprint}",
                    f"repo_commit: {head}",
                    f"feeds_config_sha256: {feeds_conf_sha}",
                    f"feeds: {feed_line}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    print(fingerprint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
