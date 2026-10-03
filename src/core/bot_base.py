"""
Base bot module providing common functionality for both modes.
"""

import threading
import time
import ctypes
from ctypes import wintypes
from abc import ABC, abstractmethod
from typing import List, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import winsound

# Preferred input backend: pywin32 (win32api/win32con) drives the mouse more
# reliably than raw ctypes on SRO_Client, and pygetwindow restores/foregrounds
# the game window. Both are optional: if they are missing we fall back to the
# raw ctypes implementation so the bot still starts.
try:
    import win32api
    import win32con
    _HAS_WIN32API = True
except ImportError:  # pragma: no cover - depends on host environment
    win32api = None
    win32con = None
    _HAS_WIN32API = False

try:
    import pygetwindow as gw
    _HAS_PYGETWINDOW = True
except ImportError:  # pragma: no cover - depends on host environment
    gw = None
    _HAS_PYGETWINDOW = False

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
    
    def _click_at(self, x: int, y: int, delay_ms: int = 50) -> None:
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
        """
        try:
            if self._click_via_send_input(x, y, delay_ms):
                self._log(f"Clicked at ({x}, {y}) [SendInput]")
                return

            if self._click_via_set_cursor_pos(x, y, delay_ms):
                self._log(f"Clicked at ({x}, {y}) [SetCursorPos + mouse_event]")
                return

            self._log(
                f"Click FAILED at ({x}, {y}): the cursor could not be positioned. "
                "If the game runs as Administrator, restart this tool as "
                "Administrator too (Windows blocks synthetic input otherwise)."
            )
        except Exception as e:
            self._log(f"Click error: {e}")
    
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
    def _window_title_candidates(window_title: str) -> List[str]:
        """
        Build the ordered list of title fragments used to locate the game window.

        The caller's title comes first so the parameter actually matters; the
        well-known SRO variants are appended as fallbacks.

        Args:
            window_title: Primary (partial) window title to search for

        Returns:
            De-duplicated list of title fragments
        """
        candidates: List[str] = []
        for name in (window_title, "SRO_Client", "Silkroad"):
            if name and name not in candidates:
                candidates.append(name)
        return candidates

    def _bring_window_to_front(self, window_title: str = "SRO_Client") -> bool:
        """
        Bring a window to the foreground by partial title match.
        
        Args:
            window_title: Partial window title to search for (default: SRO_Client)
            
        Returns:
            True if window was found and activated, False otherwise
        """
        try:
            # Preferred path: pygetwindow restores and foregrounds the window.
            if _HAS_PYGETWINDOW:
                for name in self._window_title_candidates(window_title):
                    try:
                        windows = gw.getWindowsWithTitle(name)
                    except Exception:
                        windows = []
                    for window in windows:
                        try:
                            if window.isMinimized:
                                window.restore()
                            window.activate()
                            time.sleep(0.4)  # Wait for the window to come to front
                            self._log(f"Activated window: {window.title}")
                            return True
                        except Exception as e:
                            self._log(
                                f"pygetwindow activate failed ({window.title}): {e}"
                            )

            import ctypes
            from ctypes import wintypes
            
            user32 = ctypes.windll.user32
            
            # Find window by partial title
            candidates = self._window_title_candidates(window_title)
            hwnd = None
            found_title = ""
            
            def enum_windows_callback(handle, _):
                nonlocal hwnd, found_title
                length = user32.GetWindowTextLengthW(handle)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(handle, buffer, length + 1)
                    title = buffer.value
                    # Check every candidate fragment against the window title
                    if any(name.lower() in title.lower() for name in candidates):
                        hwnd = handle
                        found_title = title
                        return False
                return True
            
            # Enumerate all windows
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
            
            if hwnd:
                # Bring window to front - multiple methods for reliability
                # Method 1: ShowWindow
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                
                # Method 2: SetForegroundWindow
                user32.SetForegroundWindow(hwnd)
                
                # Method 3: BringWindowToTop
                user32.BringWindowToTop(hwnd)
                
                # Method 4: Simulate Alt key to bypass foreground lock
                user32.keybd_event(0x12, 0, 0, 0)  # Alt down
                user32.SetForegroundWindow(hwnd)
                user32.keybd_event(0x12, 0, 2, 0)  # Alt up
                
                time.sleep(0.5)  # Wait for window to come to front
                self._log(f"Activated window: {found_title}")
                return True
            else:
                self._log(f"SRO_Client window not found! Make sure game is running.")
                return False
                
        except Exception as e:
            self._log(f"Error activating window: {e}")
            return False
    
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
