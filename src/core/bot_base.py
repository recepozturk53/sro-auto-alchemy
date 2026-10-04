"""
Base bot module providing common functionality for both modes.
"""

import os
import sys
import threading
import time
import traceback
import ctypes
from ctypes import wintypes
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import winsound

import cv2
import numpy as np

from .config import config_manager
from .screen_capture import screen_capture
from .ocr import ocr_processor, ParseResult, DEFAULT_OCR_SCALE

# Preferred input backend: pywin32 (win32api/win32con) drives the mouse more
# reliably than raw ctypes on SRO_Client. It is optional: if it is missing we
# fall back to the raw ctypes implementation so the bot still starts.
try:
    import win32api
    import win32con
    _HAS_WIN32API = True
except ImportError:  # pragma: no cover - depends on host environment
    win32api = None
    win32con = None
    _HAS_WIN32API = False

# --- Game window ------------------------------------------------------------
# The only supported client: E:\Games\Oasis 2005 MACRO\Macro_Client.exe, whose
# top-level window is titled "SRO_Client" with the MaxiGuard window class.
GAME_PROCESS_NAME = "macro_client.exe"
GAME_WINDOW_CLASS = "MaxiGuard"
GAME_WINDOW_TITLE = "SRO_Client"

# --- Fuse result wait -------------------------------------------------------
# After a click the fuse button turns into "Cancel" until the result is logged;
# the bot polls the log ROI instead of clicking again after a fixed delay.
RESULT_POLL_INTERVAL_S = 0.25
RESULT_TIMEOUT_MS = 20000

# Extra OCR passes used to cross-check a result: (scale, threshold shift, psm)
ALT_OCR_PASSES = ((2, 30, 4), (2, -30, 6), (3, 0, 6), (4, 0, 6))
# Identical passes needed to accept a result that cannot be chain-checked /
# whose chain is broken for every pass (e.g. the item was switched)
MIN_AGREEING_PASSES = 2
MIN_AGREEING_PASSES_CHAIN_BROKEN = 3
# New-line detection (_new_line_strip): two text lines are the same line when
# their text pixels differ by at most this fraction
LINE_MAX_MISMATCH = 0.12
# Rows kept around the strip of new lines handed to OCR
NEW_STRIP_MARGIN_ROWS = 2
# Where captures of an unreadable result are saved (next to logs/bot.log)
DEBUG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "logs"
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002

# Private DLL handles so the restype/argtypes below do not leak into other
# modules that use ctypes.windll.
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsHungAppWindow.argtypes = [wintypes.HWND]
_user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.InternalGetWindowText.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

DWMWA_CLOAKED = 14
try:
    _dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover - dwmapi exists on every supported Windows
    _dwmapi = None

# --- SendInput plumbing -----------------------------------------------------
# SRO reads mouse input from the Raw Input queue (DirectInput). SetCursorPos and
# mouse_event only inject at the top-level message queue, so the game ignores
# them; SendInput also feeds the Raw Input queue and therefore reaches the game.
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class _MOUSEINPUT(ctypes.Structure):
    """Win32 MOUSEINPUT."""

    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _KEYBDINPUT(ctypes.Structure):
    """Win32 KEYBDINPUT - present so the INPUT union keeps its real size."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    """Win32 HARDWAREINPUT - present so the INPUT union keeps its real size."""

    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    """The union inside Win32 INPUT."""

    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    """
    Win32 INPUT.

    The union must keep its full size (40 bytes on x64): a struct holding only
    MOUSEINPUT makes SendInput reject the call.
    """

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class BotState(Enum):
    """Bot execution states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class StopReason(Enum):
    """Reasons for bot stopping."""
    TARGET_REACHED = "target_reached"
    CRITICAL_FAILURE = "critical_failure"
    USER_STOPPED = "user_stopped"
    ERROR = "error"


@dataclass
class BotStatus:
    """Current status of the bot."""
    state: BotState = BotState.IDLE
    message: str = ""
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    iterations: int = 0
    failures: int = 0
    stop_reason: Optional[StopReason] = None


class BotBase(ABC):
    """
    Abstract base class for bot implementations.
    Provides threading, state management, and common utilities.
    """
    
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._state_lock = threading.RLock()
        self._status = BotStatus()
        self._on_status_change: Optional[Callable[[BotStatus], None]] = None
        self._on_log: Optional[Callable[[str], None]] = None
        self._animation_delay = 1500  # ms; set by subclass configure()
        # Last accepted result, to check the next one chains onto it
        self._previous_result: Optional[ParseResult] = None

    @property
    def status(self) -> BotStatus:
        """Get current bot status (thread-safe)."""
        with self._state_lock:
            return self._status
    
    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._thread is not None and self._thread.is_alive()
    
    def set_callbacks(
        self, 
        on_status_change: Optional[Callable[[BotStatus], None]] = None,
        on_log: Optional[Callable[[str], None]] = None
    ) -> None:
        """Set callback functions for status updates and logging."""
        self._on_status_change = on_status_change
        self._on_log = on_log
    
    def _update_status(self, **kwargs) -> None:
        """Update status and notify callback."""
        with self._state_lock:
            for key, value in kwargs.items():
                if hasattr(self._status, key):
                    setattr(self._status, key, value)
            
            if self._on_status_change:
                self._on_status_change(self._status)
    
    def _log(self, message: str) -> None:
        """Log a message."""
        if self._on_log:
            self._on_log(message)
        print(f"[Bot] {message}")
    
    def _click_at(self, x: int, y: int, delay_ms: int = 50) -> bool:
        """
        Perform a mouse click at the given screen coordinates.

        Tries SendInput first (it feeds the Raw Input queue that DirectInput
        games like SRO actually read), then falls back to SetCursorPos +
        mouse_event. The cursor is verified before pressing, so a blocked click
        never lands on a random spot.

        Args:
            x: X coordinate
            y: Y coordinate
            delay_ms: Delay between down and up events

        Returns:
            True when the click was delivered from the correct position
        """
        try:
            if self._click_via_send_input(x, y, delay_ms):
                self._log(f"Clicked at ({x}, {y}) [SendInput]")
                return True

            if self._click_via_set_cursor_pos(x, y, delay_ms):
                self._log(f"Clicked at ({x}, {y}) [SetCursorPos + mouse_event]")
                return True

            self._log(
                f"Click FAILED at ({x}, {y}): the cursor could not be positioned. "
                "If the game runs as Administrator, restart this tool as "
                "Administrator too (Windows blocks synthetic input otherwise)."
            )
        except Exception as e:
            self._log(f"Click error: {e}")
        return False

    def _abort_blocked_click(self) -> None:
        """
        Stop the bot after a click Windows refused to deliver.

        Running OCR after a click that never happened only re-reads the old
        log, so the loop is stopped with a clear reason instead.
        """
        self._abort(
            "Mouse input blocked: SRO_Client runs as Administrator and this "
            "tool does not. Restart the tool and accept the UAC prompt."
        )

    def _abort(self, reason: str) -> None:
        """Stop the bot from its own thread with a FAILED status and alarm."""
        self._update_status(
            state=BotState.FAILED, message=reason, stop_reason=StopReason.ERROR
        )
        self._log(f"STOPPED: {reason}")
        self._play_alarm("failure")
        self._stop_event.set()

    @staticmethod
    def _is_elevated() -> bool:
        """Whether this process runs with Administrator privileges."""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def _to_virtual_desktop(x: int, y: int) -> Tuple[int, int]:
        """
        Convert screen pixels to the 0..65535 range SendInput expects.

        Uses the full virtual desktop, so multi-monitor setups keep working.

        Args:
            x: X coordinate in screen pixels
            y: Y coordinate in screen pixels

        Returns:
            Normalised (dx, dy) for MOUSEEVENTF_ABSOLUTE
        """
        user32 = ctypes.windll.user32
        left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = max(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN), 1)
        height = max(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN), 1)
        nx = int(round((x - left) * 65535 / max(width - 1, 1)))
        ny = int(round((y - top) * 65535 / max(height - 1, 1)))
        return max(0, min(65535, nx)), max(0, min(65535, ny))

    @staticmethod
    def _send_mouse_input(flags: int, dx: int = 0, dy: int = 0) -> bool:
        """
        Inject one mouse event through SendInput.

        Args:
            flags: MOUSEEVENTF_* flags
            dx: Absolute X (0..65535) when MOUSEEVENTF_ABSOLUTE is set
            dy: Absolute Y (0..65535) when MOUSEEVENTF_ABSOLUTE is set

        Returns:
            True when the event was accepted
        """
        user32 = ctypes.windll.user32
        event = _INPUT(
            type=INPUT_MOUSE,
            mi=_MOUSEINPUT(
                dx=dx, dy=dy, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None
            ),
        )
        return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(_INPUT)) == 1

    @staticmethod
    def _cursor_position() -> Optional[Tuple[int, int]]:
        """Current cursor position in screen pixels (None when unavailable)."""
        point = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
        return None

    def _cursor_near(self, x: int, y: int, tolerance: int = 3) -> bool:
        """Whether the cursor ended up at (or very near) the target point."""
        position = self._cursor_position()
        if position is None:
            return False
        return abs(position[0] - x) <= tolerance and abs(position[1] - y) <= tolerance

    def _set_cursor_pos(self, x: int, y: int) -> bool:
        """Move the cursor, preferring pywin32. Returns True when it worked."""
        if _HAS_WIN32API:
            try:
                win32api.SetCursorPos((x, y))
                return True
            except Exception as e:
                self._log(f"win32api.SetCursorPos failed: {e}")
        return bool(ctypes.windll.user32.SetCursorPos(x, y))

    def _mouse_button_event(self, flag: int) -> bool:
        """Send one left-button down/up event through pywin32 or ctypes."""
        if _HAS_WIN32API:
            try:
                win32api.mouse_event(flag, 0, 0, 0, 0)
                return True
            except Exception as e:
                self._log(f"win32api.mouse_event failed: {e}")
        return bool(ctypes.windll.user32.mouse_event(flag, 0, 0, 0, 0))

    def _click_via_send_input(self, x: int, y: int, delay_ms: int) -> bool:
        """
        Move + click through SendInput - the path games actually listen to.

        Returns:
            True when the click was sent from the correct position
        """
        nx, ny = self._to_virtual_desktop(x, y)
        moved = self._send_mouse_input(
            MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny
        )
        if not moved:
            return False

        time.sleep(0.03)  # Let the cursor settle before pressing
        if not self._cursor_near(x, y):
            # Accepted by the API but the cursor did not follow: an elevated
            # foreground window is swallowing synthetic input.
            self._log("SendInput move ignored (cursor did not move)")
            return False

        self._send_mouse_input(MOUSEEVENTF_LEFTDOWN)
        time.sleep(delay_ms / 1000.0)
        self._send_mouse_input(MOUSEEVENTF_LEFTUP)
        return True

    def _click_via_set_cursor_pos(self, x: int, y: int, delay_ms: int) -> bool:
        """
        Fallback: SetCursorPos + mouse_event (top-level message queue).

        Returns:
            True when the click was sent from the correct position
        """
        if not self._set_cursor_pos(x, y):
            return False

        time.sleep(0.05)  # Wait for the cursor to move
        if not self._cursor_near(x, y):
            self._log("SetCursorPos ignored (cursor did not move)")
            return False

        self._mouse_button_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(delay_ms / 1000.0)
        self._mouse_button_event(MOUSEEVENTF_LEFTUP)
        return True

    @staticmethod
    def _process_image_name(pid: int) -> Optional[str]:
        """
        Lower-case executable name of a process (None when it cannot be read).

        PROCESS_QUERY_LIMITED_INFORMATION works for elevated processes too.
        """
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buffer))
            if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return buffer.value.replace("/", "\\").rsplit("\\", 1)[-1].lower()
        finally:
            _kernel32.CloseHandle(handle)

    @staticmethod
    def _window_text(hwnd: int) -> str:
        """
        Window title WITHOUT sending a message to the window.

        GetWindowTextLength/GetWindowText send WM_GETTEXT(LENGTH) and block
        forever on a hung window once this tool runs elevated (UIPI no longer
        rejects the message). InternalGetWindowText never sends messages.
        """
        buffer = ctypes.create_unicode_buffer(512)
        _user32.InternalGetWindowText(hwnd, buffer, len(buffer))
        return buffer.value

    @staticmethod
    def _window_class(hwnd: int) -> str:
        """Window class name (read locally, no message is sent)."""
        buffer = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value

    def _find_game_window(self, window_title: str = GAME_WINDOW_TITLE) -> Optional[int]:
        """
        Locate the game window: a visible top-level window of Macro_Client.exe.

        Only Macro_Client.exe is targeted; other SRO clients are ignored. When
        the process name cannot be read, the MaxiGuard window class is used.

        Args:
            window_title: Title fragment preferred among the process' windows

        Returns:
            The window handle, or None when the game is not running
        """
        matches: List[Tuple[int, int]] = []  # (priority, hwnd)
        names = {}

        def callback(hwnd, _):
            if not _user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in names:
                names[pid.value] = self._process_image_name(pid.value)
            exe = names[pid.value]
            window_class = self._window_class(hwnd)
            if exe != GAME_PROCESS_NAME and not (
                exe is None and window_class == GAME_WINDOW_CLASS
            ):
                return True
            title = self._window_text(hwnd)
            priority = 0
            if window_class == GAME_WINDOW_CLASS:
                priority += 2
            if window_title and window_title.lower() in title.lower():
                priority += 1
            if priority:
                matches.append((priority, hwnd))
            return True

        _user32.EnumWindows(_WNDENUMPROC(callback), 0)
        if not matches:
            return None
        return max(matches, key=lambda match: match[0])[1]

    @staticmethod
    def _is_cloaked(hwnd: int) -> bool:
        """Whether DWM hides the window although it is WS_VISIBLE (e.g. UWP)."""
        if _dwmapi is None:
            return False
        cloaked = wintypes.DWORD()
        result = _dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        return result == 0 and cloaked.value != 0

    def _windows_covering(self, game_hwnd: int, roi: Tuple[int, int, int, int]) -> List[str]:
        """
        Names of visible windows above the game that overlap the log area.

        EnumWindows walks top-level windows in Z-order (topmost first), so
        every window seen before the game is above it. Only local calls are
        used (no messages), so a hung window cannot block this.

        Args:
            game_hwnd: The game window
            roi: Log area (x, y, width, height)
        """
        x, y, width, height = roi
        covering: List[str] = []

        def callback(hwnd, _):
            if hwnd == game_hwnd:
                return False  # Everything after this is below the game
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            if self._is_cloaked(hwnd):
                return True
            rect = wintypes.RECT()
            if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            if (rect.left < x + width and rect.right > x
                    and rect.top < y + height and rect.bottom > y):
                name = self._window_text(hwnd) or self._window_class(hwnd)
                covering.append(name.strip())
            return True

        _user32.EnumWindows(_WNDENUMPROC(callback), 0)
        return covering

    @staticmethod
    def _display_affinity(hwnd: int) -> int:
        """
        SetWindowDisplayAffinity value of a window (0 = capturable).

        1 (WDA_MONITOR) makes captures black, 0x11 (WDA_EXCLUDEFROMCAPTURE)
        shows what is BEHIND the window - anti-cheats use these against bots.
        """
        affinity = wintypes.DWORD()
        if _user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity)):
            return affinity.value
        return 0

    def _log_capture_diagnostics(self) -> None:
        """Log why the log area may not show the game (for a failed read)."""
        try:
            hwnd = self._find_game_window()
            if not hwnd:
                self._log("Diagnostics: game window not found")
                return
            roi = config_manager.get_log_roi()
            rect = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(rect))
            foreground = _user32.GetForegroundWindow()
            self._log(
                "Diagnostics: "
                f"game foreground={foreground == hwnd} "
                f"(foreground: {self._window_text(foreground) or self._window_class(foreground)!r}), "
                f"minimized={bool(_user32.IsIconic(hwnd))}, "
                f"visible={bool(_user32.IsWindowVisible(hwnd))}, "
                f"rect=({rect.left},{rect.top},{rect.right},{rect.bottom}), "
                f"log area={roi}, "
                f"display affinity=0x{self._display_affinity(hwnd):x}, "
                f"covered by={self._windows_covering(hwnd, roi) or 'nothing'}"
            )
        except Exception as e:
            self._log(f"Diagnostics failed: {e}")

    def _ensure_log_area_visible(self, reported: set) -> None:
        """
        Make sure the game - not another window - is what the log area shows.

        Called on every poll. Re-activates the game when a window covers the
        log area, and reports (once per cause) what was found.

        Args:
            reported: Causes already logged during this wait
        """
        hwnd = self._find_game_window()
        if not hwnd:
            return
        affinity = self._display_affinity(hwnd)
        if affinity and "affinity" not in reported:
            reported.add("affinity")
            self._log(
                f"WARNING: the game hides itself from screen capture "
                f"(display affinity 0x{affinity:x}) - the log cannot be read "
                "from the screen while this is active"
            )
        covering = self._windows_covering(hwnd, config_manager.get_log_roi())
        if covering:
            key = "covered:" + "|".join(covering)
            if key not in reported:
                reported.add(key)
                self._log(f"Log area covered by {covering} - bringing the game back")
            self._bring_window_to_front()

    def _bring_window_to_front(self, window_title: str = GAME_WINDOW_TITLE) -> bool:
        """
        Bring the Macro_Client.exe game window to the foreground.

        Every call here is non-blocking: a hung game window must never freeze
        the bot thread.

        Args:
            window_title: Title fragment preferred among the process' windows

        Returns:
            True if the game window is in the foreground, False otherwise
        """
        try:
            hwnd = self._find_game_window(window_title)
            if not hwnd:
                self._log(
                    f"Game window not found ({GAME_PROCESS_NAME} / {window_title}). "
                    "Make sure the game is running."
                )
                return False

            if _user32.IsHungAppWindow(hwnd):
                self._log("WARNING: SRO_Client is not responding (window hung)")
                return False

            if _user32.GetForegroundWindow() == hwnd:
                return True

            if _user32.IsIconic(hwnd):
                _user32.ShowWindowAsync(hwnd, SW_RESTORE)

            if not _user32.SetForegroundWindow(hwnd):
                # Alt key press lifts the foreground lock for this process
                _user32.keybd_event(VK_MENU, 0, 0, 0)
                _user32.SetForegroundWindow(hwnd)
                _user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

            time.sleep(0.3)  # Wait for the window to come to front
            if _user32.GetForegroundWindow() == hwnd:
                self._log(f"Activated window: {self._window_text(hwnd)}")
                return True
            self._log("WARNING: Could not bring SRO_Client to the foreground")
            return False

        except Exception as e:
            self._log(f"Error activating window: {e}")
            return False

    def _capture_log_text(self) -> Tuple[np.ndarray, str]:
        """Capture the log ROI and OCR it. Returns (image, text)."""
        x, y, width, height = config_manager.get_log_roi()
        image = screen_capture.capture_region(x, y, width, height)
        return image, self._ocr(image)

    @staticmethod
    def _ocr(
        image: np.ndarray,
        scale: int = DEFAULT_OCR_SCALE,
        threshold_shift: int = 0,
        psm: Optional[int] = None,
    ) -> str:
        """OCR a log image with the configured PSM/threshold (overridable)."""
        config = config_manager.config
        return ocr_processor.extract_text(
            image,
            config.tesseract_psm if psm is None else psm,
            config.ocr_threshold + threshold_shift,
            scale,
        )

    @staticmethod
    def _chains(previous: ParseResult, current: ParseResult) -> Optional[bool]:
        """
        Whether `current` starts where `previous` ended.

        A stat log reads "[old -> new]" and the next one's "old" is this one's
        "new", e.g. (549~644)->(538~630) then (538~630)->(551~646). A misread
        digit almost always breaks that link.

        Returns:
            True/False, or None when the results cannot be chained
        """
        prev, cur = previous.value, current.value
        if not (isinstance(prev, dict) and isinstance(cur, dict)):
            return None
        if "new_range" in prev and "old_range" in cur:
            return tuple(cur["old_range"]) == tuple(prev["new_range"])
        if "new_value" in prev and "old_value" in cur:
            return cur["old_value"] == prev["new_value"]
        return None

    def _confirm_result(
        self,
        image: np.ndarray,
        result: ParseResult,
        reread: Callable[[str], ParseResult],
    ) -> Optional[ParseResult]:
        """
        Decide whether an OCR result can be trusted, re-reading if needed.

        One misread digit (5 vs 6) can decide whether the target was reached.
        A reading is accepted when it chains onto the previous result. When no
        chain is known, MIN_AGREEING_PASSES identical OCR passes are needed;
        when the chain is broken (e.g. another item), the stricter
        MIN_AGREEING_PASSES_CHAIN_BROKEN. A reading identical to the previous
        result that does not chain is the OLD result read again: rejected.

        Args:
            image: The capture the result was read from
            result: The candidate result
            reread: Extracts the newest result from another OCR pass' text

        Returns:
            The trusted result, or None
        """
        previous = self._previous_result

        def same(a: ParseResult, b: ParseResult) -> bool:
            return (a.success and b.success and a.result_type == b.result_type
                    and a.value == b.value)

        def readings():
            yield result
            for scale, shift, psm in ALT_OCR_PASSES:
                yield reread(self._ocr(image, scale, shift, psm))

        seen: List[ParseResult] = []
        chain_known = False
        for reading in readings():
            link = self._chains(previous, reading) if previous else None
            if link is True:
                return reading
            if previous is not None and same(reading, previous):
                seen.append(reading)
                continue  # the old result, not a new one
            chain_known = chain_known or link is not None
            needed = (
                MIN_AGREEING_PASSES_CHAIN_BROKEN if chain_known
                else MIN_AGREEING_PASSES
            )
            if reading.success and 1 + sum(same(reading, s) for s in seen) >= needed:
                if chain_known:
                    self._log(
                        "WARNING: result does not follow the previous one "
                        f"({previous.value}); accepted because "
                        f"{needed} OCR passes agree"
                    )
                return reading
            seen.append(reading)

        self._log(
            "OCR passes disagree: "
            + " / ".join(str(r.value if r.success else r.error) for r in seen)
        )
        return None

    @staticmethod
    def _text_mask(image: np.ndarray) -> np.ndarray:
        """Boolean text-pixel mask of a log capture (scrollbar removed)."""
        gray = cv2.cvtColor(ocr_processor.crop_scrollbar(image), cv2.COLOR_BGR2GRAY)
        return gray > config_manager.config.ocr_threshold

    @staticmethod
    def _line_bands(mask: np.ndarray) -> List[Tuple[int, int]]:
        """(top, bottom) row ranges of the text lines in a mask, top first."""
        inked = mask.any(axis=1)
        bands: List[Tuple[int, int]] = []
        row, height = 0, len(inked)
        while row < height:
            if inked[row]:
                top = row
                while row < height and inked[row]:
                    row += 1
                bands.append((top, row))
            else:
                row += 1
        return bands

    @staticmethod
    def _same_line(a: np.ndarray, b: np.ndarray) -> bool:
        """Whether two line masks show the same text (pixel comparison)."""
        if abs(a.shape[0] - b.shape[0]) > 1:
            return False
        rows = min(a.shape[0], b.shape[0])
        a, b = a[:rows], b[:rows]
        ink = np.count_nonzero(a | b)
        return ink == 0 or np.count_nonzero(a ^ b) / ink <= LINE_MAX_MISMATCH

    @classmethod
    def _new_line_strip(
        cls, before: np.ndarray, after: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        The part of `after` holding lines that were not in `before`.

        The game appends messages at the bottom and drops whole lines at the
        top, so the lines of `after` are a tail of `before`'s lines followed
        by the new ones. Lines are compared by their pixels, so a result that
        reads exactly like the previous one (e.g. (139.9 ~ 171.0) twice) is
        still recognised as new, and wrapped lines / OCR noise do not matter.
        Lines cut by the top edge, and a static bottom band present at the
        same place in both captures (the panel icon), are ignored.

        Returns:
            The strip of new lines (BGR), or None when nothing is new
        """
        old_mask, new_mask = cls._text_mask(before), cls._text_mask(after)
        if old_mask.shape != new_mask.shape:
            return after
        height = old_mask.shape[0]
        old_bands = [b for b in cls._line_bands(old_mask) if b[0] > 0]
        new_bands = [b for b in cls._line_bands(new_mask) if b[0] > 0]

        # Static band at the very bottom (panel icon): same place, same pixels
        if (old_bands and new_bands and old_bands[-1] == new_bands[-1]
                and old_bands[-1][1] == height
                and cls._same_line(old_mask[slice(*old_bands[-1])],
                                   new_mask[slice(*new_bands[-1])])):
            old_bands, new_bands = old_bands[:-1], new_bands[:-1]

        old_lines = [old_mask[top:bottom] for top, bottom in old_bands]
        new_lines = [new_mask[top:bottom] for top, bottom in new_bands]

        start = 0  # first new line in new_bands
        for overlap in range(min(len(old_lines), len(new_lines)), 0, -1):
            if all(cls._same_line(o, n) for o, n in
                   zip(old_lines[-overlap:], new_lines[:overlap])):
                start = overlap
                break
        if start >= len(new_bands):
            return None  # every line was already there
        top = max(new_bands[start][0] - NEW_STRIP_MARGIN_ROWS, 0)
        bottom = min(new_bands[-1][1] + NEW_STRIP_MARGIN_ROWS, height)
        return after[top:bottom]

    @staticmethod
    def _pick_event(events: List[ParseResult]) -> Optional[ParseResult]:
        """The fuse result among new events: the newest stat, else a failure."""
        for wanted in ("stat", "failed"):
            for event in reversed(events):
                if event.result_type == wanted:
                    return event
        return None

    def _fuse_and_wait(self, mode: str) -> Optional[ParseResult]:
        """
        Click fuse once and wait until the game logs its result.

        While the fuse animation runs the button turns into "Cancel", so a
        second click before the result is logged cancels the fuse. The button
        is therefore never clicked again until a NEW result line shows up in
        the log ROI (or RESULT_TIMEOUT_MS passes).

        Args:
            mode: "plus" or "stat" (selects the parser)

        Returns:
            The parsed result; None when the bot was stopped, the click could
            not be delivered, or no result could be read (the bot is then
            stopped too: clicking again blindly could cancel a fuse or throw
            away a stat that already reached the target)
        """
        fuse_x, fuse_y = config_manager.get_fuse_button()
        parse = (
            ocr_processor.parse_plus_result if mode == "plus"
            else ocr_processor.parse_stat_result
        )

        def newest_stat(text: str) -> ParseResult:
            events = ocr_processor.stat_events(text)
            if events:
                return events[-1]
            return ParseResult(success=False, result_type="unknown",
                               raw_text=text, error="No stat result")

        # 1. Bring SRO window to front BEFORE clicking
        if not self._bring_window_to_front():
            self._log("WARNING: Could not activate SRO window, trying anyway...")
        time.sleep(0.3)  # Wait for window to be active

        # 2. Remember the log as it is now, to tell the new result apart
        baseline_image, baseline_text = self._capture_log_text()
        last_image = baseline_image
        self._log(f"Log area before click: {self._one_line(baseline_text)}")
        if self._previous_result is None:
            # The last result already on screen anchors the chain check
            on_screen = newest_stat(baseline_text) if mode == "stat" else parse(baseline_text)
            if on_screen.success:
                self._previous_result = on_screen

        # 3. Click the fuse button (exactly once per result)
        self._log(f"Clicking fuse button at ({fuse_x}, {fuse_y})")
        if not self._click_at(fuse_x, fuse_y, 50):
            self._abort_blocked_click()
            return None

        # 4. The result cannot arrive before the animation ends
        self._log(f"Waiting for fuse result (at least {self._animation_delay}ms)...")
        if self._stop_event.wait(self._animation_delay / 1000.0):
            return None
        self._bring_window_to_front()

        # 5. Poll the log until a new, parseable result line appears
        timeout_s = max(RESULT_TIMEOUT_MS, self._animation_delay) / 1000.0
        deadline = time.time() + timeout_s
        unparsed = ""
        image, text = baseline_image, baseline_text
        reported: set = set()
        while time.time() < deadline:
            self._ensure_log_area_visible(reported)
            image, text = self._capture_log_text()
            if not text.strip() and baseline_text.strip() and "empty" not in reported:
                reported.add("empty")
                self._log("WARNING: log area reads empty after the click")
                self._log_capture_diagnostics()
            if last_image is None or not np.array_equal(image, last_image):
                last_image = image
                result, reread, fresh, strip = self._detect_new_result(
                    mode, baseline_image, image, parse, newest_stat
                )
                if result is not None:
                    self._log(
                        f"OCR Result: {result.result_type} - "
                        f"{self._one_line(result.raw_text)}"
                    )
                    confirmed = self._confirm_result(strip, result, reread)
                    if confirmed is not None:
                        self._previous_result = confirmed
                        return confirmed
                    # Re-read on the next poll even if nothing moves
                    last_image = None
                elif fresh:
                    unparsed = fresh  # e.g. a chat line; keep waiting
            if self._stop_event.wait(RESULT_POLL_INTERVAL_S):
                return None

        self._log(f"Log area at timeout: {self._one_line(text)}")
        self._log_capture_diagnostics()
        self._save_debug_images(baseline_image, image)
        self._abort(
            f"No readable fuse result in the log within {timeout_s:.0f}s - "
            "stopped instead of clicking again. Check the item and the log area."
            + (f" Last new text: {unparsed[:100]}" if unparsed else "")
        )
        return None

    def _detect_new_result(
        self,
        mode: str,
        baseline_image: np.ndarray,
        image: np.ndarray,
        parse: Callable[[str], ParseResult],
        newest_stat: Callable[[str], ParseResult],
    ) -> Tuple[Optional[ParseResult], Callable[[str], ParseResult], str, np.ndarray]:
        """
        Find a result that appeared in the log since the click.

        Only the strip of NEW lines (see _new_line_strip) is read, so results
        already on screen can never be taken for the new one.

        Returns:
            (candidate or None, function reading the result from another OCR
            pass of the strip, OCR text of the strip, the strip image)
        """
        strip = self._new_line_strip(baseline_image, image)
        if strip is None or strip.shape[0] == 0:
            return None, newest_stat, "", image
        text = self._ocr(strip)
        if mode == "stat":
            return (self._pick_event(ocr_processor.stat_events(text)),
                    newest_stat, text, strip)
        result = parse(text)
        return (result if result.success else None), parse, text, strip

    @staticmethod
    def _one_line(text: str, limit: int = 160) -> str:
        """OCR text squeezed onto one log line ("<empty>" when nothing read)."""
        flat = " | ".join(line.strip() for line in text.splitlines() if line.strip())
        if not flat:
            return "<empty>"
        return flat[:limit] + "..." if len(flat) > limit else flat

    def _save_debug_images(self, before: np.ndarray, after: np.ndarray) -> None:
        """
        Save what the bot saw before the click and at the end of the wait.

        Written to logs/ (raw capture + the binarized image Tesseract got), so
        a failed read can be diagnosed from the files.
        """
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            config = config_manager.config
            for name, image in (("before", before), ("after", after)):
                raw_path = os.path.join(DEBUG_DIR, f"fuse_{name}.png")
                cv2.imwrite(raw_path, image)
                cv2.imwrite(
                    os.path.join(DEBUG_DIR, f"fuse_{name}_ocr.png"),
                    ocr_processor.preprocess_image(image, config.ocr_threshold),
                )
            self._log(
                f"Debug images saved to {os.path.abspath(DEBUG_DIR)} "
                "(fuse_before*.png / fuse_after*.png)"
            )
        except Exception as e:
            self._log(f"Could not save debug images: {e}")

    def _play_alarm(self, sound_type: str = "success") -> None:
        """
        Play an alarm sound.
        
        Args:
            sound_type: "success", "failure", or "warning"
        """
        try:
            if sound_type == "success":
                # Ascending tones for success
                for freq in [523, 659, 784, 1047]:
                    winsound.Beep(freq, 200)
            elif sound_type == "failure":
                # Descending tones for failure
                for freq in [400, 300, 200]:
                    winsound.Beep(freq, 300)
            elif sound_type == "warning":
                # Alert tone
                winsound.Beep(1000, 500)
        except Exception as e:
            self._log(f"Sound error: {e}")
    
    def start(self) -> bool:
        """
        Start the bot in a background thread.
        
        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running:
            self._log("Bot is already running")
            return False

        if not self._is_elevated():
            self._log(
                "WARNING: Not running as Administrator. If SRO_Client runs "
                "elevated, Windows blocks synthetic mouse input and the fuse "
                "button will never be clicked - restart this tool as Administrator."
            )
        
        self._stop_event.clear()
        self._pause_event.clear()
        self._previous_result = None
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        self._update_status(state=BotState.RUNNING, message="Bot started")
        self._log("Bot started")
        return True
    
    def stop(self) -> None:
        """Stop the bot."""
        if not self.is_running:
            return
        
        self._stop_event.set()
        self._pause_event.set()  # Release any pause
        
        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                # Stuck inside a blocking call: show where, for diagnosis
                frame = sys._current_frames().get(self._thread.ident)
                if frame is not None:
                    stack = "".join(traceback.format_stack(frame))
                    self._log(f"Bot thread did not stop; stuck at:\n{stack}")
            self._thread = None
        
        self._update_status(
            state=BotState.STOPPED, 
            message="Bot stopped",
            stop_reason=StopReason.USER_STOPPED
        )
        self._log("Bot stopped by user")
    
    def pause(self) -> None:
        """Pause the bot."""
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._update_status(state=BotState.RUNNING, message="Bot resumed")
            self._log("Bot resumed")
        else:
            self._pause_event.set()
            self._update_status(state=BotState.PAUSED, message="Bot paused")
            self._log("Bot paused")
    
    def _check_pause_stop(self) -> bool:
        """
        Check if bot should pause or stop.
        
        Returns:
            True if bot should stop, False otherwise
        """
        # Check for stop
        if self._stop_event.is_set():
            return True
        
        # Check for pause (blocks until resumed)
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.1)
        
        return self._stop_event.is_set()
    
    @abstractmethod
    def _run_loop(self) -> None:
        """Main bot loop (implemented by subclasses)."""
        pass
    
    @abstractmethod
    def _perform_iteration(self) -> bool:
        """
        Perform one iteration of the bot logic.
        
        Returns:
            True if target reached, False otherwise
        """
        pass
