#!/usr/bin/env python3
"""Validate that the agent knowledge map matches the actual repository.

Checks:
  1. docs/module-index.json is valid JSON with the expected shape.
  2. Every file listed for a module exists on disk.
  3. Every Python source file is owned by exactly one module.
  4. Every referenced doc file exists.
  5. Every markdown link in docs/ and AGENTS.md resolves.
  6. Every task has read/edit/verify entries.
  7. Module dependency edges obey the layering rules (no upward imports).

Exit code 0 when everything passes, 1 otherwise.

Usage:
    python tools/verify_docs.py
    python tools/verify_docs.py --quiet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "module-index.json"

# Dependency direction: a module may depend on its own layer or any layer
# ranked LOWER here. L0 (entrypoint) is the top of the stack, L4 (config) the
# base that everything may lean on.
LAYER_ORDER = {"L0": 4, "L1": 3, "L2": 2, "L3": 1, "L4": 0}

SOURCE_DIRS = ["src"]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class Report:
    def __init__(self, quiet: bool = False) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks = 0
        self.quiet = quiet

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.errors.append(message)
        return condition

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def ok(self, message: str) -> None:
        if not self.quiet:
            print(f"  [ok] {message}")


def discover_sources() -> set:
    """Return mapped source files, ignoring package markers (__init__.py)."""
    found = set()
    for d in SOURCE_DIRS:
        base = ROOT / d
        if base.exists():
            for p in base.rglob("*.py"):
                if p.name == "__init__.py":
                    continue
                found.add(p.relative_to(ROOT).as_posix())
    return found

def verify(report: Report) -> None:
    # --- 1. index loads -----------------------------------------------------
    if not report.check(INDEX.exists(), f"missing index: {INDEX}"):
        return
    try:
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.check(False, f"module-index.json is not valid JSON: {exc}")
        return
    report.ok("module-index.json parses as JSON")

    modules = data.get("modules", {})
    tasks = data.get("tasks", {})
    report.check(bool(modules), "no modules defined")
    report.check(bool(tasks), "no tasks defined")
    report.ok(f"{len(modules)} modules, {len(tasks)} tasks")
# --- 2/3. modules and ownership ----------------------------------------
    owned: dict = {}
    for mid, mod in modules.items():
        files = mod.get("files", [])
        report.check(bool(files), f"module '{mid}' lists no files")
        for rel in files:
            owned.setdefault(rel, []).append(mid)
            report.check((ROOT / rel).exists(), f"module '{mid}': missing file {rel}")
        report.check(mod.get("layer") in LAYER_ORDER,
                     f"module '{mid}': invalid layer {mod.get('layer')!r}")
        report.check(bool(mod.get("doc")), f"module '{mid}': no doc path")
        report.check(bool(mod.get("role")), f"module '{mid}': no role")

    for rel, owners in owned.items():
        report.check(len(owners) == 1,
                     f"{rel} is claimed by multiple modules: {owners}")

    sources = discover_sources()
    for src in sorted(sources):
        report.check(src in owned, f"unmapped source file: {src}")
    if sources:
        report.ok(f"{len(sources)} source files, all mapped to a module")

    # --- 6. tasks -----------------------------------------------------------
    for key, task in tasks.items():
        report.check(bool(task.get("summary")), f"task '{key}': no summary")
        report.check(bool(task.get("edit")), f"task '{key}': no edit entry")
        report.check(bool(task.get("read")), f"task '{key}': no read entry")
        report.check(bool(task.get("verify")), f"task '{key}': no verify entry")
        for rel in task.get("edit", []):
            report.check((ROOT / rel).exists(),
                         f"task '{key}': edit target missing: {rel}")
        for rel in task.get("read", []):
            report.check((ROOT / rel).exists(),
                         f"task '{key}': read target missing: {rel}")
    report.ok("all tasks have summary/read/edit/verify and resolvable paths")

    # --- 4. doc targets exist ----------------------------------------------
    for mid, mod in modules.items():
        doc = mod.get("doc")
        if doc:
            report.check((ROOT / doc).exists(), f"module '{mid}': missing doc {doc}")
    for key in ("conventions_doc", "gotchas_doc", "glossary_doc"):
        rel = data.get(key)
        if rel:
            report.check((ROOT / rel).exists(), f"{key}: missing {rel}")
    report.ok("referenced documentation files exist")

    # --- 5. markdown links resolve -----------------------------------------
    md_files = [ROOT / "AGENTS.md", ROOT / "README.md"]
    md_files += sorted((ROOT / "docs").rglob("*.md"))
    for md in md_files:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if not (md.parent / clean).resolve().exists():
                report.errors.append(
                    f"broken link in {md.relative_to(ROOT).as_posix()}: {target}")
    report.ok(f"markdown links checked across {len(md_files)} files")

    # --- 7. layering --------------------------------------------------------
    for mid, mod in modules.items():
        layer = mod.get("layer")
        for dep in mod.get("depends_on", []):
            dep_mod = modules.get(dep)
            if dep_mod is None:
                report.errors.append(f"module '{mid}': unknown dependency '{dep}'")
                continue
            if LAYER_ORDER.get(dep_mod["layer"], 99) > LAYER_ORDER.get(layer, 0):
                report.errors.append(
                    f"layer violation: {mid} ({layer}) depends on {dep} "
                    f"({dep_mod['layer']}) - must not depend upward")
    report.ok("module dependency edges respect layer order")

    # --- warnings (informational) ------------------------------------------
    adr = ROOT / "docs" / "adr"
    if not adr.exists() or not any(adr.glob("*.md")):
        report.warn("docs/adr/ has no decision records yet")
    for rel, owners in sorted(owned.items()):
        mod = modules[owners[0]]
        doc_path = ROOT / mod["doc"]
        if doc_path.exists():
            doc_text = doc_path.read_text(encoding="utf-8", errors="replace")
            if rel not in doc_text and Path(rel).name not in doc_text:
                report.warn(f"{mod['doc']} never mentions {rel}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args()

    report = Report(quiet=args.quiet)
    print("Verifying agent knowledge map...")
    verify(report)

    if report.warnings:
        print(f"\nWarnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  [warn] {w}")

    if report.errors:
        print(f"\nFAILED ({len(report.errors)} errors, {report.checks} checks):")
        for e in report.errors:
            print(f"  [FAIL] {e}")
        return 1

    print(f"\nPASSED: {report.checks} checks, 0 errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())