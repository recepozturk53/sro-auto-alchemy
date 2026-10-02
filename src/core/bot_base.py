"""
Base bot module providing common functionality for both modes.
"""

import threading
import time
import ctypes
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
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
        Perform a mouse click at specified coordinates.

        Uses pywin32 (win32api/win32con) when available - the approach proven
        to work on SRO_Client - and falls back to the raw ctypes mouse_event
        calls otherwise.

        Args:
            x: X coordinate
            y: Y coordinate
            delay_ms: Delay between down and up events
        """
        try:
            if _HAS_WIN32API:
                # Move cursor to position, then press and release the button.
                win32api.SetCursorPos((x, y))
                time.sleep(0.05)  # Wait for the cursor to move
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0
                )
                time.sleep(delay_ms / 1000.0)
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0
                )
            else:
                user32 = ctypes.windll.user32
                user32.SetCursorPos(x, y)
                time.sleep(0.05)  # Wait for the cursor to move

                MOUSEDOWN = 0x0002  # MOUSEEVENTF_LEFTDOWN
                MOUSEUP = 0x0004    # MOUSEEVENTF_LEFTUP

                user32.mouse_event(MOUSEDOWN, 0, 0, 0, 0)
                time.sleep(delay_ms / 1000.0)
                user32.mouse_event(MOUSEUP, 0, 0, 0, 0)

            self._log(f"Clicked at ({x}, {y})")

        except Exception as e:
            self._log(f"Click error: {e}")
    
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
