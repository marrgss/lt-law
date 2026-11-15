#!/usr/bin/env python3
"""Publish the code as a snapshot commit in the public repository (D-055).

Usage: uv run bin/publish_code.py [--ref origin/main] [--message "…"] [--push]

The working history stays private (D-022): the public repository gets one commit per publication, holding the tracked
files of --ref and nothing else, authored with the account's GitHub noreply address. Steps:
  1. export --ref's tracked files (git archive) into out/public/ (its own git repository; cloned from the remote
     `public` when that already has commits, so a publication is a new commit on top);
  2. scan every file and the commit message: the built-in patterns below (local paths, mail addresses other than the
     project's, wording about who asked for what) and the private ones in private/public_scan.txt (one regular
     expression a line: names and other identifiers that must never be published; the file itself is not tracked).
     A hit stops the run and lists the lines;
  3. commit; with --push, push to the remote `public` (set once: git remote add public <url>).
Without --push nothing leaves this machine: the commit waits in out/public/ to be looked at.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / "out" / "public"
PRIVATE_PATTERNS = ROOT / "private" / "public_scan.txt"
SKIP = {"uv.lock", "deploy/package-lock.json"}
# mail addresses that are public on purpose: the project's, sources' and examples'
MAIL_OK = re.compile(r"@(atviri-teises-aktai\.lt|example\.com|users\.noreply\.github\.com|stat\.gov\.lt|vssa\.lt|eso\.lt)$|"
                     r"<name>@<project>|\.iam\.gserviceaccount\.com$", re.I)
BUILT_IN = [
    (r"(?-i:/home/[a-z][\w.-]*/|/Users/[\w.-]+/|[A-Z]:\\Users\\)", "a local path"),
    (r"\bthe owner\b|\bowner's (call|word|focus|areas|question|priorit|employer|decision|permission)|\(owner[ ,:]|\bowner:|\bowner,? \d{4}-", "who asked (say what was decided)"),
    (r"\bemployer\b(?! or\b)(?!;)", "an employer"),
    (r"proceed as you see fit|side-activity", "working conversation"),
    (r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_\w{30,}|-----BEGIN [A-Z ]*PRIVATE KEY", "a credential"),
]
MAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|<name>@<project>\S*")


def run(*cmd, cwd=ROOT, check=True, **kw) -> str:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, **kw).stdout.strip()


def patterns() -> list[tuple[re.Pattern, str]]:
    out = [(re.compile(p, re.I), why) for p, why in BUILT_IN]
    if PRIVATE_PATTERNS.exists():
        out += [(re.compile(l.strip(), re.I), "private/public_scan.txt") for l in PRIVATE_PATTERNS.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    else:
        print(f"note: no {PRIVATE_PATTERNS.relative_to(ROOT)} (names and identifiers to keep out): only the built-in patterns run")
    return out


def scan(root: pathlib.Path, message: str) -> list[str]:
    pats, hits = patterns(), []
    texts = [("(commit message)", message)]
    for f in sorted(p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts):
        rel = f.relative_to(root).as_posix()
        if rel in SKIP:
            continue
        try:
            texts.append((rel, f.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            hits.append(f"{rel}: not text (look at it by hand)")
    for rel, text in texts:
        for n, line in enumerate(text.splitlines(), 1):
            for rx, why in pats:
                if rel == "bin/publish_code.py" and why != "private/public_scan.txt":
                    continue  # this file spells the built-in patterns out
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {why}: {line.strip()[:140]}")
            for m in MAIL.findall(line):
                if not MAIL_OK.search(m):
                    hits.append(f"{rel}:{n}: a mail address: {m}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="origin/main", help="what to publish (default: origin/main)")
    ap.add_argument("--message", default="", help="one line about what changed, in words for outside readers")
    ap.add_argument("--author", default="", help='"name <address>" (default: the gh account with its noreply address)')
    ap.add_argument("--push", action="store_true", help="push to the remote `public` after the commit")
    a = ap.parse_args()

    author = a.author
    if not author:
        u = json.loads(run("gh", "api", "user"))
        author = f"{u['login']} <{u['id']}+{u['login']}@users.noreply.github.com>"
    name, mail = re.fullmatch(r"(.+?) <(.+)>", author).groups()
    remote = run("git", "remote", "get-url", "public", check=False)
    if a.push and not remote:
        sys.exit("no remote `public`: git remote add public <the public repository's URL>")

    if not (WORK / ".git").exists():
        WORK.mkdir(parents=True, exist_ok=True)
        has = remote and run("git", "ls-remote", "--heads", remote, "main", check=False)
        if has:
            run("git", "clone", "-q", "--branch", "main", remote, str(WORK), cwd=ROOT)
        else:
            run("git", "init", "-q", "-b", "main", cwd=WORK)
    for p in WORK.iterdir():  # the tree is replaced whole: a file dropped from --ref is dropped here
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    tar = subprocess.run(["git", "archive", a.ref], cwd=ROOT, check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(WORK)], input=tar, check=True)

    message = f"Code as of {dt.date.today().isoformat()}" + (f": {a.message}" if a.message else "")
    hits = scan(WORK, message)
    if hits:
        print(f"NOT published: {len(hits)} lines to reword first", *hits[:60], sep="\n  ")
        return 1
    run("git", "add", "-A", cwd=WORK)
    if not run("git", "status", "--porcelain", cwd=WORK):
        print("nothing changed since the last publication")
        return 0
    run("git", "-c", f"user.name={name}", "-c", f"user.email={mail}", "commit", "-q", "-m", message, cwd=WORK)
    files = len(run("git", "ls-files", cwd=WORK).splitlines())
    print(f"committed in {WORK.relative_to(ROOT)}: {run('git', 'log', '--format=%h %an <%ae> %s', '-1', cwd=WORK)} ({files} files, "
          f"{len(run('git', 'rev-list', 'HEAD', cwd=WORK).splitlines())} commits)")
    if a.push:
        subprocess.run(["git", "push", "-q", remote, "main"], cwd=WORK, check=True)
        print(f"pushed to {remote}")
    else:
        print("not pushed (--push)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
