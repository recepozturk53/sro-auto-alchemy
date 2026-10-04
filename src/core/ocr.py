"""
OCR module for parsing game log text using OpenCV + Tesseract.
Implements thresholding preprocessing and strict regex parsing.
"""

import os
import re
import shutil
import cv2
import numpy as np
import pytesseract
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from PIL import Image
import threading

# Nearest-neighbour upscale factor for the 1-px bitmap log font. Measured on
# the game log: x2 reads every digit/bracket correctly at thresholds 120..180;
# x3 reads "646]" as "6463", x4 reads "538" as "638".
DEFAULT_OCR_SCALE = 2

# Scrollbar detection (crop_scrollbar): search the right 15% of the log area
# for a column whose pixels are bright over >= 60% of its height (the bar's
# border), and cut a few pixels left of it.
SCROLLBAR_SEARCH_FRACTION = 0.15
SCROLLBAR_MIN_COLUMN_FILL = 0.6
SCROLLBAR_MARGIN_PX = 6


def _tesseract_path_candidates() -> Tuple[str, ...]:
    """
    Well-known Windows locations of tesseract.exe, plus the TESSERACT_CMD override.

    Returns:
        Ordered tuple of candidate paths (may contain empty strings)
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    return (
        os.environ.get("TESSERACT_CMD", ""),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(local_appdata, "Programs", "Tesseract-OCR", "tesseract.exe"),
        os.path.join(local_appdata, "Tesseract-OCR", "tesseract.exe"),
    )


def locate_tesseract() -> Tuple[bool, str]:
    """
    Point pytesseract at a working tesseract.exe and verify that it runs.

    Tries the PATH lookup first (pytesseract default), then the common install
    directories and the TESSERACT_CMD environment variable. Verifying with
    get_tesseract_version() means a broken or missing binary is reported as
    unavailable instead of failing silently on every OCR call.

    Returns:
        Tuple of (available, detail) where detail is the detected version string
        or the last error message
    """
    last_error = ""

    # 1. Default: pytesseract resolves "tesseract" from PATH.
    try:
        return True, str(pytesseract.get_tesseract_version())
    except Exception as exc:
        last_error = str(exc)

    # 2. Known / explicit install locations.
    for candidate in _tesseract_path_candidates():
        if not candidate or not os.path.isfile(candidate):
            continue
        pytesseract.pytesseract.tesseract_cmd = candidate
        try:
            return True, str(pytesseract.get_tesseract_version())
        except Exception as exc:
            last_error = str(exc)

    # 3. Last resort: whatever shutil.which() can find.
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        try:
            return True, str(pytesseract.get_tesseract_version())
        except Exception as exc:
            last_error = str(exc)

    return False, last_error


@dataclass
class ParseResult:
    """Result of parsing game log."""
    success: bool
    result_type: str  # "plus", "stat", "failed", "unknown"
    value: Optional[Any] = None
    raw_text: str = ""
    error: Optional[str] = None


class OCRProcessor:
    """
    OCR processor for game log parsing.
    Uses OpenCV thresholding + Tesseract with strict regex patterns.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Regex patterns for parsing game log
    # Plus patterns: +1, +2, etc. also handles "Item +5" format
    PLUS_PATTERN = re.compile(r'\+\s*(\d+)', re.IGNORECASE)
    PLUS_ALT_PATTERN = re.compile(r'plus\s*(\d+)|item\s*\+\s*(\d+)', re.IGNORECASE)
    FAILED_PATTERN = re.compile(r'failed|fail|error|unsuccessful', re.IGNORECASE)
    SUCCESS_PATTERN = re.compile(r'success|succeeded', re.IGNORECASE)
    
    # Stat patterns (OCR-tolerant: brackets are often misread as ( ) { } j f,
    # so they are optional; the "->" arrow is required). Examples:
    #   ...changed to [(549 ~ 644) -> (538 ~ 630)]      (range)
    #   ...changed to [(82.9%~98.6%) -> (81.6%~97.1%)]  (percent range)
    #   ...changed to [12.2->12.4]  /  (297->301]         (single value)
    _NUM = r'(\d+(?:\.\d+)?)'
    _ARROW = r'\s*-+\s*>\s*'
    _RANGE = _NUM + r'\s*%?\s*[~-]\s*' + _NUM + r'\s*%?'
    STAT_RANGE_PATTERN = re.compile(
        _RANGE + r'\s*[)\]}jJ|]?' + _ARROW + r'[(\[{fF]?\s*' + _RANGE
    )
    STAT_SIMPLE_PATTERN = re.compile(r'[\[(]\s*' + _NUM + _ARROW + _NUM)
    # Bare "N->N" only counts when the text looks like a stat change message
    STAT_ARROW_PATTERN = re.compile(_NUM + _ARROW + _NUM)
    STAT_MESSAGE_HINT = re.compile(r'chang', re.IGNORECASE)
    # "The alchemy enhancement has failed." - tied to alchemy wording so a chat
    # line containing "fail" is not mistaken for a fuse result
    ALCHEMY_FAILED_PATTERN = re.compile(
        r'(?:alch|enhanc)[^\n]*?fail', re.IGNORECASE
    )

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._ocr_lock = threading.RLock()
            # Locate and verify the Tesseract engine once at startup.
            self._tesseract_available, self._tesseract_detail = locate_tesseract()
            self._initialized = True

    @property
    def is_tesseract_available(self) -> bool:
        """Whether a working Tesseract engine was detected."""
        return self._tesseract_available

    def tesseract_info(self) -> str:
        """Human-readable Tesseract status (version string or error message)."""
        return self._tesseract_detail
    
    @staticmethod
    def crop_scrollbar(image: np.ndarray, threshold: int = 150) -> np.ndarray:
        """
        Cut the log panel's scrollbar off the right edge of a capture.

        The selected log area usually includes the scrollbar, which Tesseract
        reads as junk at line ends ("- 4 [a Ta"); one such "4" landed inside
        a wrapped range ("(139.9 % ~ 4 / 171.0 %)") and broke it. The bar has
        a bright vertical border; no text column is that bright that tall.

        Args:
            image: BGR capture of the log area
            threshold: Gray level counted as bright

        Returns:
            The capture without the scrollbar (unchanged when none is found)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        width = gray.shape[1]
        start = int(width * (1 - SCROLLBAR_SEARCH_FRACTION))
        bright = (gray[:, start:] > threshold).mean(axis=0)
        columns = np.nonzero(bright >= SCROLLBAR_MIN_COLUMN_FILL)[0]
        if columns.size == 0:
            return image
        cut = max(start + int(columns[0]) - SCROLLBAR_MARGIN_PX, 1)
        return image[:, :cut]

    def preprocess_image(
        self, image: np.ndarray, threshold: int = 150, scale: int = DEFAULT_OCR_SCALE
    ) -> np.ndarray:
        """
        Preprocess image for OCR.

        SRO draws its log with a 1-px bitmap font (no anti-aliasing) over a
        dark, semi-transparent panel. So the crop is binarized FIRST with a
        fixed threshold and only then upscaled with nearest-neighbour, which
        keeps the glyphs crisp. Blur / cubic upscaling / Otsu smear the 1-px
        strokes and make Tesseract read 5 as 6 and ] as j.

        Args:
            image: BGR numpy array
            threshold: Gray level separating text from background (90..150 all
                work on the game log)
            scale: Integer nearest-neighbour upscale factor

        Returns:
            Preprocessed image: black text on white
        """
        with self._ocr_lock:
            gray = cv2.cvtColor(self.crop_scrollbar(image), cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

            # Game logs are light text on a dark background, but Tesseract
            # expects dark text on a light background - invert when needed.
            if float(np.mean(mask)) < 127.0:
                mask = cv2.bitwise_not(mask)

            if scale > 1:
                mask = cv2.resize(
                    mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST
                )

            # Tesseract reads more reliably with a clean white margin.
            return cv2.copyMakeBorder(
                mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255
            )
    
    def extract_text(
        self,
        image: np.ndarray,
        psm: int = 6,
        threshold: int = 150,
        scale: int = DEFAULT_OCR_SCALE,
    ) -> str:
        """
        Extract text from image using Tesseract OCR.

        Args:
            image: BGR numpy array
            psm: Tesseract page segmentation mode (default 6)
            threshold: Threshold for preprocessing
            scale: Nearest-neighbour upscale factor (see preprocess_image)

        Returns:
            Extracted text string
        """
        with self._ocr_lock:
            # Retry locating Tesseract; the engine may have been installed while
            # the application was already running.
            if not self._tesseract_available:
                self._tesseract_available, self._tesseract_detail = locate_tesseract()
            if not self._tesseract_available:
                print(
                    "OCR Error: Tesseract engine not found "
                    f"({self._tesseract_detail}). Install Tesseract or set TESSERACT_CMD."
                )
                return ""

            try:
                # Preprocess the image
                processed = self.preprocess_image(image, threshold, scale)
                
                # Configure Tesseract
                config = f'--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789+-.>%~[]()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ '
                
                # Run OCR
                text = pytesseract.image_to_string(processed, config=config)
                
                return text.strip()
            except Exception as e:
                print(f"OCR Error: {e}")
                return ""
    
    def parse_plus_result(self, text: str) -> ParseResult:
        """
        Parse plus upgrade result from log text.
        
        Args:
            text: OCR extracted text
            
        Returns:
            ParseResult with plus level or failure status
        """
        with self._ocr_lock:
            # Check for failure first
            if self.FAILED_PATTERN.search(text):
                return ParseResult(
                    success=True,
                    result_type="failed",
                    raw_text=text
                )
            
            # Look for plus pattern: +1, +2, etc.
            match = self.PLUS_PATTERN.search(text)
            if match:
                plus_level = int(match.group(1))
                return ParseResult(
                    success=True,
                    result_type="plus",
                    value=plus_level,
                    raw_text=text
                )
            
            # Try alternative plus patterns
            alt_match = self.PLUS_ALT_PATTERN.search(text)
            if alt_match:
                # Check which group matched
                for group in alt_match.groups():
                    if group:
                        plus_level = int(group)
                        return ParseResult(
                            success=True,
                            result_type="plus",
                            value=plus_level,
                            raw_text=text
                        )
            
            # Check for success indicator (might show plus level)
            if self.SUCCESS_PATTERN.search(text):
                # Try to find any number that might be the plus level
                numbers = re.findall(r'\b(\d+)\b', text)
                for num in numbers:
                    level = int(num)
                    if 1 <= level <= 20:  # Reasonable plus level range
                        return ParseResult(
                            success=True,
                            result_type="plus",
                            value=level,
                            raw_text=text
                        )
            
            # Unknown result
            return ParseResult(
                success=False,
                result_type="unknown",
                raw_text=text,
                error="Could not parse plus result"
            )
    
    @staticmethod
    def _plausible_range(
        old_min: float, old_max: float, new_min: float, new_max: float
    ) -> bool:
        """
        Reject range readings that cannot be real.

        min <= max must hold on both sides, and a fuse never moves a bound by
        more than 2x. Typical OCR slips fail this: 5->6 gives "638 ~ 630",
        a "]" read as "3" gives "551 ~ 6463".
        """
        if old_min > old_max or new_min > new_max:
            return False
        for old, new in ((old_min, new_min), (old_max, new_max)):
            if old > 0 and not 0.5 <= new / old <= 2.0:
                return False
        return True

    def stat_events(self, text: str) -> List[ParseResult]:
        """
        Every stat fuse result in the log text, oldest first.

        A result often wraps over 2-3 lines ("...changed to [(126.5 % ~ 155.1"
        / "%)]."), so comparing lines cannot tell an old result from a new
        one. Comparing the parsed results can: the log scrolls, so the events
        after a fuse are the old ones (minus some at the top) plus the new one.

        Args:
            text: OCR extracted text

        Returns:
            "stat" results (range or single value) and "failed" results, in
            the order they appear
        """
        with self._ocr_lock:
            found: List[Tuple[int, ParseResult]] = []
            taken: List[Tuple[int, int]] = []

            for match in self.STAT_RANGE_PATTERN.finditer(text):
                values = tuple(float(v) for v in match.groups())
                if not self._plausible_range(*values):
                    continue
                taken.append(match.span())
                found.append((match.start(), self.parse_stat_result(match.group(0))))

            def free(span: Tuple[int, int]) -> bool:
                return all(span[1] <= a or span[0] >= b for a, b in taken)

            singles = list(self.STAT_SIMPLE_PATTERN.finditer(text))
            if self.STAT_MESSAGE_HINT.search(text):
                singles += list(self.STAT_ARROW_PATTERN.finditer(text))
            for match in singles:
                if not free(match.span()):
                    continue
                taken.append(match.span())
                old_value, new_value = (float(v) for v in match.groups())
                found.append((match.start(), ParseResult(
                    success=True,
                    result_type="stat",
                    value={
                        'old_value': old_value,
                        'new_value': new_value,
                        'improved': new_value > old_value
                    },
                    raw_text=match.group(0)
                )))

            for match in self.ALCHEMY_FAILED_PATTERN.finditer(text):
                found.append((match.start(), ParseResult(
                    success=True, result_type="failed", raw_text=match.group(0)
                )))

            return [result for _, result in sorted(found, key=lambda item: item[0])]

    def parse_stat_result(self, text: str) -> ParseResult:
        """
        Parse stat upgrade result from log text.

        Handles (newest = LAST match in the text wins):
        - [(549 ~ 644) -> (538 ~ 630)]   -> new_range / new_max / new_avg
        - [(82.9%~98.6%) -> (81.6%~97.1%)]
        - [12.2->12.4] or (297->301]     -> new_value

        Args:
            text: OCR extracted text

        Returns:
            ParseResult with stat values
        """
        with self._ocr_lock:
            # Ranges first: their numbers would otherwise be read as N->N.
            # Newest plausible match wins; misreads usually break plausibility.
            ranges = [
                values for values in (
                    tuple(float(v) for v in match.groups())
                    for match in self.STAT_RANGE_PATTERN.finditer(text)
                )
                if self._plausible_range(*values)
            ]
            if ranges:
                old_min, old_max, new_min, new_max = ranges[-1]
                old_avg = (old_min + old_max) / 2
                new_avg = (new_min + new_max) / 2
                return ParseResult(
                    success=True,
                    result_type="stat",
                    value={
                        'old_range': (old_min, old_max),
                        'new_range': (new_min, new_max),
                        'old_avg': old_avg,
                        'new_avg': new_avg,
                        'new_max': new_max,
                        'improved': new_max > old_max
                    },
                    raw_text=text
                )

            singles = list(self.STAT_SIMPLE_PATTERN.finditer(text))
            if not singles and self.STAT_MESSAGE_HINT.search(text):
                singles = list(self.STAT_ARROW_PATTERN.finditer(text))
            if singles:
                old_value, new_value = (float(v) for v in singles[-1].groups())
                return ParseResult(
                    success=True,
                    result_type="stat",
                    value={
                        'old_value': old_value,
                        'new_value': new_value,
                        'improved': new_value > old_value
                    },
                    raw_text=text
                )

            # Check for failure
            if self.FAILED_PATTERN.search(text):
                return ParseResult(
                    success=True,
                    result_type="failed",
                    raw_text=text
                )
            
            # Unknown result
            return ParseResult(
                success=False,
                result_type="unknown",
                raw_text=text,
                error="Could not parse stat result"
            )
    
    def process_log_region(
        self, 
        image: np.ndarray, 
        mode: str = "plus",
        threshold: int = 150,
        psm: int = 6
    ) -> ParseResult:
        """
        Process a log region image and parse the result.
        
        Args:
            image: BGR numpy array of log region
            mode: "plus" or "stat" mode
            threshold: Threshold for preprocessing
            psm: Tesseract PSM mode
            
        Returns:
            ParseResult with parsed data
        """
        with self._ocr_lock:
            # Extract text
            text = self.extract_text(image, psm, threshold)
            
            if not text:
                return ParseResult(
                    success=False,
                    result_type="unknown",
                    error="No text extracted"
                )
            
            # Parse based on mode
            if mode == "plus":
                return self.parse_plus_result(text)
            elif mode == "stat":
                return self.parse_stat_result(text)
            else:
                return ParseResult(
                    success=False,
                    result_type="unknown",
                    error=f"Unknown mode: {mode}"
                )
    
    def debug_save_preprocessed(self, image: np.ndarray, filepath: str, threshold: int = 150) -> None:
        """
        Save preprocessed image for debugging OCR issues.
        
        Args:
            image: BGR numpy array
            filepath: Path to save image
            threshold: Threshold value
        """
        processed = self.preprocess_image(image, threshold)
        cv2.imwrite(filepath, processed)


# Global instance
ocr_processor = OCRProcessor()
