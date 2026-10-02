#!/usr/bin/env python3
"""Print the minimal context an agent needs for a task.

Reads docs/module-index.json and resolves a task keyword (or a free-text
description) to the small set of files that must be read and the files that
must be edited.

Usage:
    python tools/ctx.py ocr
    python tools/ctx.py "add a new stat log format"
    python tools/ctx.py bot --json
    python tools/ctx.py --list
    python tools/ctx.py --module core-ocr
    python tools/ctx.py --file src/core/ocr.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "module-index.json"

STOPWORDS = {
    "i", "we", "to", "the", "a", "an", "and", "or", "of", "in", "on", "for",
    "with", "add", "make", "new", "please", "want", "need", "how", "do",
    "this", "that", "is", "are", "be", "it", "my", "me",
}


def load_index() -> dict:
    if not INDEX.exists():
        sys.exit(f"ERROR: index not found: {INDEX}")
    with INDEX.open(encoding="utf-8") as fh:
        return json.load(fh)


def tokenize(text: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in STOPWORDS}


def score_task(query: set, key: str, task: dict) -> int:
    """Score a task: exact/fuzzy key match dominates, then token overlap."""
    score = 0
    if key in query:
        score += 10
    elif tokenize(key) & query:
        score += 5

    haystack = set()
    haystack |= tokenize(str(task.get("summary", "")))
    haystack |= tokenize(key)
    for path in task.get("edit", []):
        haystack |= tokenize(path)
    overlap = query & haystack
    score += len(overlap)
    # Summary hits are stronger than incidental path matches.
    score += 2 * len(query & tokenize(str(task.get("summary", ""))))
    # Keywords are curated vocabulary; multi-word hits count fully.
    for kw in task.get("keywords", []):
        kw_tokens = tokenize(kw)
        if kw_tokens and kw_tokens <= query:
            score += 4
    return score


def print_task(key: str, task: dict, modules: dict) -> None:
    print(f"\n=== TASK: {key} ===")
    print(f"{task.get('summary', '')}")

    reads = list(task.get("read", []))
    for path in task.get("edit", []):
        if path not in reads:
            reads.append(path)
    if reads:
        print("\nREAD (in order):")
        for path in reads:
            print(f"  - {path}")
        print("\nThen read AGENTS.md: architecture and rules table.")

    edits = task.get("edit", [])
    if edits:
        print("\nEDIT:")
        for path in edits:
            print(f"  - {path}")
            for mid, mod in modules.items():
                if path in mod.get("files", []):
                    print(f"      module: {mid} (layer {mod['layer']}) -> {mod['doc']}")
                    break

    for rule in task.get("rules", []):
        print(f"\nRULE: {rule}")

    for cmd in task.get("verify", []):
        print(f"VERIFY: {cmd}")


def print_module(mid: str, mod: dict) -> None:
    print(f"\n=== MODULE: {mid} (layer {mod['layer']}) ===")
    print(f"files: {', '.join(mod['files'])}")
    print(f"doc:   {mod['doc']}")
    print(f"role:  {mod['role']}")
    if mod.get("symbols"):
        print("symbols:")
        for sym in mod["symbols"]:
            print(f"  - {sym}")
    if mod.get("depends_on"):
        print("depends_on: " + ", ".join(mod["depends_on"]))
    for rule in mod.get("rules", []):
        print(f"rule: {rule}")


def module_for_file(modules: dict, target: str):
    for mid, mod in modules.items():
        if target in mod.get("files", []):
            return mid, mod
    return None, None
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*", help="task keyword or free text")
    parser.add_argument("--list", action="store_true", help="list all tasks")
    parser.add_argument("--module", help="show a module entry")
    parser.add_argument("--file", help="show which modules/tasks touch a file")
    parser.add_argument("--json", action="store_true", help="machine readable output")
    args = parser.parse_args()

    data = load_index()
    tasks = data.get("tasks", {})
    modules = data.get("modules", {})

    if args.list:
        print("TASKS:")
        for key, task in tasks.items():
            print(f"  {key:<12} {task.get('summary','')}")
        print("\nMODULES:")
        for key, mod in modules.items():
            print(f"  {key:<24} {mod['layer']}  {mod['files']}")
        return 0

    if args.module:
        if args.module not in modules:
            sys.exit(f"ERROR: unknown module '{args.module}'. Try --list")
        if args.json:
            print(json.dumps({args.module: modules[args.module]}, indent=2))
        else:
            print_module(args.module, modules[args.module])
        return 0

    if args.file:
        target = args.file.replace("\\", "/")
        mid, mod = module_for_file(modules, target)
        if mod is None:
            sys.exit(f"ERROR: no module claims {target}")
        print_module(mid, mod)
        related = [k for k, t in tasks.items()
                   if any(target in p for p in t.get("edit", []))]
        print("\nTasks that edit this file: " + (", ".join(related) or "none"))
        return 0

    if not args.query:
        parser.print_help()
        return 1

    query = tokenize(" ".join(args.query))
    ranked = sorted(((score_task(query, k, t), k) for k, t in tasks.items()), reverse=True)

    if args.json:
        best = [k for score, k in ranked if score > 0] or [ranked[0][1]]
        print(json.dumps({k: tasks[k] for k in best}, indent=2))
        return 0

    print(f"Query tokens: {sorted(query)}")
    best = [(s, k) for s, k in ranked if s > 0][:3]
    if not best:
        print("\nNo keyword match; showing all tasks (use --list for a summary).")
        best = list(ranked)
    for _, key in best:
        print_task(key, tasks[key], modules)
    print("\nContext protocol: AGENTS.md -> task doc(s) above -> edit files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())