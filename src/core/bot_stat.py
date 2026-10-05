"""
Stat Mode bot implementation.
Clicks upgrade button, reads stat values/percentages from log.
Stops when current_stat >= target_threshold.
"""

import os
import time
from typing import Optional, Dict, Any

import cv2

from .bot_base import BotBase, BotState, StopReason, DEBUG_DIR
from .config import config_manager
from .screen_capture import screen_capture
from .ocr import ocr_processor


class StatModeBot(BotBase):
    """
    Bot for Stat upgrade mode.
    Reads stat values from game log and stops when threshold is reached.
    Supports formats:
    - [12.2->12.4]
    - [(82.9%~98.6%) -> (81.6%~97.1%)]
    """
    
    def __init__(self):
        super().__init__()
        self._current_stat = 0.0
        self._target_threshold = 100.0
        self._best_stat = 0.0
        self._worst_stat = 0.0
        self._consecutive_failures = 0
        self._max_failures = 10
        self._stone_failures = 0
        self._target_type = "range"
    
    def configure(
        self, 
        target_threshold: float,
        animation_delay: int = 1500,
        click_delay: int = 300,
        max_failures: int = 10,
        target_type: str = "range"
    ) -> None:
        """
        Configure the Stat mode bot.
        
        Args:
            target_threshold: Target stat threshold to reach
            animation_delay: Delay after clicking (ms)
            click_delay: Delay between clicks (ms)
            max_failures: Maximum consecutive failures before stopping
        """
        self._target_threshold = target_threshold
        if target_type not in ("range", "percent"):
            raise ValueError(f"Unknown stat target type: {target_type}")
        self._target_type = target_type
        self._animation_delay = animation_delay
        self._click_delay = click_delay
        self._max_failures = max_failures
        
        self._update_status(
            target_value=target_threshold,
            message=f"Configured: Target {target_threshold}"
        )
        self._log(f"Stat mode configured: Target {target_threshold}")
    
    def _run_loop(self) -> None:
        """Main bot loop for Stat mode."""
        self._log("Stat mode loop started")
        self._current_stat = 0.0
        self._best_stat = 0.0
        self._worst_stat = float('inf')
        self._consecutive_failures = 0
        self._stone_failures = 0
        
        # Get configuration
        config = config_manager.config
        
        if not config_manager.is_configured():
            self._update_status(
                state=BotState.FAILED,
                message="Bot not configured! Set fuse button and log ROI.",
                stop_reason=StopReason.ERROR
            )
            self._log("ERROR: Bot not configured!")
            return

        if self._target_type == "percent":
            hover_x, hover_y = config_manager.get_item_hover()
            _, _, roi_width, roi_height = config_manager.get_percent_roi()
            if hover_x <= 0 or hover_y <= 0 or roi_width <= 0 or roi_height <= 0:
                self._abort("Select the item hover point and percentage area first.")
                return
        
        self._update_status(
            current_value=0.0,
            iterations=0,
            failures=0
        )
        
        # Wait 1 second before starting (time to switch to game window)
        self._log("Starting in 3 seconds... Switch to game window NOW!")
        self._update_status(message="Switch to game window! Starting in 3 sec...")
        time.sleep(1)
        self._log("2 seconds...")
        time.sleep(1)
        self._log("1 second...")
        time.sleep(1)
        
        # Try to bring SRO_Client window to front
        self._bring_window_to_front("SRO_Client")
        
        while not self._check_pause_stop():
            try:
                # Perform one iteration
                target_reached = self._perform_iteration()
                
                if target_reached:
                    self._update_status(
                        state=BotState.COMPLETED,
                        message=f"Target {self._target_threshold} reached! Current: {self._current_stat}",
                        stop_reason=StopReason.TARGET_REACHED
                    )
                    self._log(f"SUCCESS: Target {self._target_threshold} reached! Current: {self._current_stat}")
                    self._play_alarm("success")
                    return
                
                # Check for too many failures
                if self._consecutive_failures >= self._max_failures:
                    self._update_status(
                        state=BotState.FAILED,
                        message=f"Too many consecutive failures ({self._max_failures})",
                        stop_reason=StopReason.CRITICAL_FAILURE
                    )
                    self._log(f"CRITICAL: {self._max_failures} consecutive failures")
                    self._play_alarm("failure")
                    return
                
                # Delay between iterations
                time.sleep(self._click_delay / 1000.0)
                
            except Exception as e:
                self._log(f"Iteration error: {e}")
                self._consecutive_failures += 1
                self._update_status(failures=self._consecutive_failures)
        
        # Stopped by user (a blocked click already recorded its own reason)
        if self._status.state != BotState.FAILED:
            self._update_status(stop_reason=StopReason.USER_STOPPED)
    
    def _perform_iteration(self) -> bool:
        """
        Perform one upgrade iteration.
        
        Returns:
            True if target reached, False otherwise
        """
        # Click once, then wait for the game to log the result: clicking
        # again during the animation would hit "Cancel" and abort the fuse.
        result = self._fuse_and_wait("stat")
        if result is None:
            return False  # Stopped by user or click blocked

        # Update iteration count
        iterations = self.status.iterations + 1
        self._update_status(iterations=iterations)
        
        # Parse result
        if result.success:
            if result.result_type == "stat":
                if self._target_type == "percent":
                    stat_value = self._read_tooltip_percent()
                    if stat_value is None:
                        return False
                else:
                    stat_value = self._extract_stat_value(result.value)
                self._consecutive_failures = 0
                
                # Track best/worst
                if stat_value > self._best_stat:
                    self._best_stat = stat_value
                if stat_value < self._worst_stat:
                    self._worst_stat = stat_value
                
                self._current_stat = stat_value
                
                self._update_status(
                    current_value=stat_value,
                    failures=0,
                    message=(f"Current: {stat_value:.2f}{'%' if self._target_type == 'percent' else ''} "
                             f"(Best: {self._best_stat:.2f})")
                )
                if self._target_type == "percent":
                    self._log(f"Tooltip percentage detected: {stat_value:g}%")
                elif 'new_range' in result.value:
                    low, high = result.value['new_range']
                    self._log(
                        f"Stat detected: new range {low:g} ~ {high:g} "
                        f"(target {self._target_threshold:g} vs {high:g})"
                    )
                else:
                    self._log(f"Stat detected: {stat_value:.2f}")
                
                # Check if target reached
                if stat_value >= self._target_threshold:
                    return True
                    
            elif result.result_type == "failed":
                # An ordinary stone failure does not change the item's stat.
                # Keep trying until the target is reached or a real error occurs.
                self._stone_failures += 1
                self._consecutive_failures = 0
                self._update_status(
                    failures=self._stone_failures,
                    message=f"Stone failed ({self._stone_failures} total); stat unchanged"
                )
                self._log(f"Stone failed ({self._stone_failures} total); stat unchanged")
        else:
            self._log(f"Failed to parse result: {result.error}")
        
        return False

    def _read_tooltip_percent(self) -> Optional[float]:
        """Hover the item and require two agreeing tooltip OCR readings."""
        hover_x, hover_y = config_manager.get_item_hover()
        roi = config_manager.get_percent_roi()
        if not self._set_cursor_pos(hover_x, hover_y):
            self._abort("Could not move cursor over the item to read its percentage.")
            return None
        time.sleep(0.4)
        if not self._cursor_near(hover_x, hover_y):
            self._abort("Cursor did not reach the item; percentage cannot be read.")
            return None

        readings = []
        for _ in range(2):
            image = screen_capture.capture_region(*roi)
            result = ocr_processor.read_tooltip_percent(image)
            if not result.success:
                try:
                    os.makedirs(DEBUG_DIR, exist_ok=True)
                    debug_path = os.path.join(DEBUG_DIR, "tooltip_percent_failed.png")
                    cv2.imwrite(debug_path, image)
                    self._log(f"Tooltip OCR image saved: {debug_path}")
                except Exception as exc:
                    self._log(f"Could not save tooltip OCR image: {exc}")
                self._abort(f"Tooltip percentage could not be read: {result.error} "
                            f"OCR: {result.raw_text!r}. Check the selected percentage area.")
                return None
            readings.append(result.value)
            if self._stop_event.wait(0.2):
                return None
        if readings[0] != readings[1]:
            self._abort(f"Tooltip percentage changed between OCR readings: {readings}. "
                        "Check the selected percentage area.")
            return None
        return readings[0]
    
    def _extract_stat_value(self, value_data: Dict[str, Any]) -> float:
        """
        Extract the current stat value from parsed data.
        
        Args:
            value_data: Parsed stat data from OCR
            
        Returns:
            Float value of the current stat
        """
        # Range format: [(549 ~ 644) -> (551 ~ 646)] - the target is compared
        # with the UPPER bound of the new range (646 here)
        if 'new_range' in value_data:
            return value_data['new_range'][1]
        
        # Simple format: [12.2->12.4]
        if 'new_value' in value_data:
            return value_data['new_value']
        
        return 0.0
    
    def get_current_stat(self) -> float:
        """Get the current detected stat value."""
        return self._current_stat
    
    def get_best_stat(self) -> float:
        """Get the best stat value encountered."""
        return self._best_stat
    
    def get_worst_stat(self) -> float:
        """Get the worst stat value encountered."""
        return self._worst_stat if self._worst_stat != float('inf') else 0.0
    
    def get_consecutive_failures(self) -> int:
        """Get the count of consecutive failures."""
        return self._consecutive_failures
