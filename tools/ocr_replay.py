#!/usr/bin/env python3
"""Replay the collected OCR samples through the current parser.

The bot saves every log strip it reads to logs/ocr_samples/ (see
src/core/ocr_samples.py): readable ones under ok/ named after the value,
unreadable ones under error/. This tool reads every PNG back, runs the live
OCR + parser over it and reports what changed - so a parser or preprocessing
change can be checked against the whole corpus instead of one screenshot.

A sample's expected value is its file name:

    ok/10_to_3_20261009-184358-701.png      -> expects 10 -> 3
    ok/549-644_to_538-630_<stamp>.png       -> expects that range
    ok/failed_<stamp>.png                   -> expects a failed fuse
    error/unreadable_timeout_<stamp>.png    -> currently unreadable

To teach the bot a misread: look at the PNG in error/, then move it to ok/
with the right value in the name ("10_to_3_<keep the stamp>.png"). The next
run shows it as a FAIL until the parser handles it, and as a PASS afterwards.

Usage:
    python tools/ocr_replay.py                 # replay everything
    python tools/ocr_replay.py --only-failures # just what does not match
    python tools/ocr_replay.py --dir <path>    # another sample folder
    python tools/ocr_replay.py --passes        # try every ALT_OCR_PASSES setting

Exit code 0 when every labelled sample parses to its label, 1 otherwise.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.bot_base import ALT_OCR_PASSES  # noqa: E402
from src.core.config import config_manager  # noqa: E402
from src.core.ocr import DEFAULT_OCR_SCALE, ParseResult, ocr_processor  # noqa: E402
from src.core.ocr_samples import ERROR_DIR, OK_DIR, SAMPLES_DIR, label_for  # noqa: E402

# "<label>_<YYYYmmdd-HHMMSS-mmm>.png"; the stamp is dropped, the rest is the label
STAMP = re.compile(r"_\d{8}-\d{6}-\d{3}$")


def expected_label(path: Path) -> str:
    """The label a sample file name claims, without the timestamp."""
    return STAMP.sub("", path.stem)


def normalise(label: str) -> str:
    """Compare labels without caring about the note suffixes added at save."""
    for note in ("_timeout", "_passes-disagree"):
        label = label.replace(note, "")
    return label.strip("_")


def read_sample(path: Path, scale: int, shift: int, psm: Optional[int]) -> ParseResult:
    """Run the live OCR + stat parser over one sample image."""
    image = cv2.imread(str(path))
    if image is None:
        return ParseResult(False, "unknown", error=f"cannot read {path.name}")
    config = config_manager.config
    text = ocr_processor.extract_text(
        image,
        config.tesseract_psm if psm is None else psm,
        config.ocr_threshold + shift,
        scale,
    )
    events = ocr_processor.stat_events(text)
    if events:
        return events[-1]
    return ParseResult(False, "unknown", raw_text=text, error="no stat result")


def samples(directory: Path) -> List[Path]:
    """Every raw sample capture in a folder, oldest first."""
    return sorted(
        p for p in directory.glob("*.png") if not p.name.endswith("_ocr.png")
    )


def replay(
    paths: List[Path], labelled: bool, passes: List[Tuple[int, int, Optional[int]]]
) -> Tuple[int, int, List[str]]:
    """
    Replay samples and collect the mismatches.

    Args:
        paths: Sample images
        labelled: Whether the file names carry an expected value (ok/) or
            just record that the strip was unreadable (error/)
        passes: (scale, threshold shift, psm) OCR settings to try per sample

    Returns:
        (matched, total, report lines)
    """
    matched = 0
    lines: List[str] = []
    for path in paths:
        want = normalise(expected_label(path))
        results = [read_sample(path, *setting) for setting in passes]
        got = [normalise(label_for(r)) for r in results]
        ok = want in got if labelled else got[0] != "unreadable"
        if ok:
            matched += 1
        detail = got[0] if len(passes) == 1 else " | ".join(dict.fromkeys(got))
        if labelled:
            lines.append(
                f"{'PASS' if ok else 'FAIL'}  {path.name}\n"
                f"        want {want}\n        got  {detail}"
            )
        else:
            lines.append(
                f"{'NOW READS' if ok else 'still unreadable'}  {path.name}\n"
                f"        got  {detail}"
            )
    return matched, len(paths), lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default=str(SAMPLES_DIR),
                        help="sample root holding ok/ and error/")
    parser.add_argument("--only-failures", action="store_true",
                        help="print only the samples that do not match")
    parser.add_argument("--passes", action="store_true",
                        help="also try the bot's alternative OCR passes")
    args = parser.parse_args()

    root = Path(args.dir)
    ok_dir = Path(OK_DIR) if root == Path(SAMPLES_DIR) else root / "ok"
    error_dir = Path(ERROR_DIR) if root == Path(SAMPLES_DIR) else root / "error"

    if not ok_dir.exists() and not error_dir.exists():
        print(f"No samples yet under {root}")
        print("Run the bot with collect_ocr_samples enabled to collect some.")
        return 0

    settings: List[Tuple[int, int, Optional[int]]] = [(DEFAULT_OCR_SCALE, 0, None)]
    if args.passes:
        settings += [tuple(p) for p in ALT_OCR_PASSES]  # type: ignore[misc]

    failures = 0
    for directory, labelled in ((ok_dir, True), (error_dir, False)):
        paths = samples(directory) if directory.exists() else []
        if not paths:
            continue
        matched, total, lines = replay(paths, labelled, settings)
        print(f"\n== {directory.name}/  {matched}/{total} "
              f"{'match their label' if labelled else 'now readable'}")
        for line in lines:
            if args.only_failures and line.startswith(("PASS", "NOW READS")):
                continue
            print(line)
        if labelled:
            failures += total - matched

    print(f"\n{failures} labelled sample(s) do not parse to their label")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
