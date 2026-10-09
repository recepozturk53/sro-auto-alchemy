"""
OCR sample collector: every log strip the bot reads is saved as a PNG whose
name says what was read from it.

The point is a growing, self-labelled corpus. Readable strips land in
logs/ocr_samples/ok/ named after the value ("10_<stamp>.png"), unreadable ones
in logs/ocr_samples/error/ with the raw OCR text next to them. The error
folder is the work queue: rename a file to the value it should have read
(ok/<value>_<stamp>.png) and tools/ocr_replay.py turns the whole corpus into a
pass/fail report, so a parser change can be checked against every sample ever
collected instead of one screenshot.
"""

import os
import re
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .ocr import ParseResult, ocr_processor

# logs/ocr_samples next to logs/bot.log
SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "logs", "ocr_samples",
)
OK_DIR = os.path.join(SAMPLES_DIR, "ok")
ERROR_DIR = os.path.join(SAMPLES_DIR, "error")

# Cap so a long session cannot fill the disk; oldest samples are dropped first.
MAX_SAMPLES_PER_DIR = 2000

# Characters kept in the label part of a file name
_LABEL_SAFE = re.compile(r"[^0-9A-Za-z._~-]+")

_write_lock = threading.Lock()


def label_for(result: Optional[ParseResult]) -> str:
    """
    Short file-name label describing what was read.

    Ranges become "549-644_to_538-630", single values "10_to_3", a failed
    fuse "failed". Unreadable results get "unreadable".
    """
    if result is None or not result.success:
        return "unreadable"
    if result.result_type == "failed":
        return "failed"
    value = result.value
    if isinstance(value, dict):
        if "new_range" in value:
            old, new = value["old_range"], value["new_range"]
            return f"{_num(old[0])}-{_num(old[1])}_to_{_num(new[0])}-{_num(new[1])}"
        if "new_value" in value:
            return f"{_num(value['old_value'])}_to_{_num(value['new_value'])}"
    if value is None:
        return result.result_type
    return _LABEL_SAFE.sub("-", str(value))


def _num(value: float) -> str:
    """A float without its trailing ".0" (549.0 -> "549")."""
    return f"{value:g}"


def _prune(directory: str) -> None:
    """Drop the oldest files once a sample folder passes MAX_SAMPLES_PER_DIR."""
    try:
        # Only the raw captures are counted; each one's "_ocr.png" / ".txt"
        # companion goes with it.
        names = [
            n for n in os.listdir(directory)
            if n.endswith(".png") and not n.endswith("_ocr.png")
        ]
        if len(names) <= MAX_SAMPLES_PER_DIR:
            return
        names.sort(key=lambda n: os.path.getmtime(os.path.join(directory, n)))
        for name in names[: len(names) - MAX_SAMPLES_PER_DIR]:
            stem = name[: -len(".png")]
            for suffix in (".png", "_ocr.png", ".txt"):
                path = os.path.join(directory, stem + suffix)
                if os.path.exists(path):
                    os.remove(path)
    except OSError:
        pass


def save_sample(
    image: np.ndarray,
    result: Optional[ParseResult],
    raw_text: str = "",
    note: str = "",
) -> Optional[str]:
    """
    Save one log strip as a labelled training sample.

    Args:
        image: The BGR strip the OCR passes ran on
        result: The accepted result, or None when nothing could be read
        raw_text: OCR text of the strip (saved beside unreadable samples)
        note: Extra word in the file name, e.g. "timeout"

    Returns:
        Path of the saved PNG, or None when nothing was saved
    """
    if image is None or getattr(image, "size", 0) == 0:
        return None

    readable = result is not None and result.success
    directory = OK_DIR if readable else ERROR_DIR
    label = label_for(result)
    if note:
        label = f"{label}_{_LABEL_SAFE.sub('-', note)}"
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"

    try:
        with _write_lock:
            os.makedirs(directory, exist_ok=True)
            png_path = os.path.join(directory, f"{label}_{stamp}.png")
            cv2.imwrite(png_path, image)
            # The binarized image Tesseract actually saw, for eyeballing
            cv2.imwrite(
                os.path.join(directory, f"{label}_{stamp}_ocr.png"),
                ocr_processor.preprocess_image(image),
            )
            if not readable:
                with open(
                    os.path.join(directory, f"{label}_{stamp}.txt"),
                    "w", encoding="utf-8",
                ) as handle:
                    handle.write(raw_text)
            _prune(directory)
        return png_path
    except Exception:
        # Sample collection must never break a running fuse loop.
        return None
