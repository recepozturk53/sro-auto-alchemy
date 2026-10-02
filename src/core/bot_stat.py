"""
Stat Mode bot implementation.
Clicks upgrade button, reads stat values/percentages from log.
Stops when current_stat >= target_threshold.
"""

import time
from typing import Optional, Dict, Any
from .bot_base import BotBase, BotState, StopReason
from .config import config_manager
from .screen_capture import screen_capture
from .ocr import ocr_processor, ParseResult


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
    
    def configure(
        self, 
        target_threshold: float,
        animation_delay: int = 1500,
        click_delay: int = 300,
        max_failures: int = 10
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
        
        # Stopped by user
        self._update_status(stop_reason=StopReason.USER_STOPPED)
    
    def _perform_iteration(self) -> bool:
        """
        Perform one upgrade iteration.
        
        Returns:
            True if target reached, False otherwise
        """
        config = config_manager.config
        fuse_x, fuse_y = config_manager.get_fuse_button()
        log_roi = config_manager.get_log_roi()
        
        # 1. Bring SRO window to front BEFORE clicking
        if not self._bring_window_to_front():
            self._log("WARNING: Could not activate SRO window, trying anyway...")
        
        time.sleep(0.3)  # Wait for window to be active
        
        # 2. Click the fuse button
        self._log(f"Clicking fuse button at ({fuse_x}, {fuse_y})")
        self._click_at(fuse_x, fuse_y, 50)
        
        # 3. Wait for animation AND for new log to appear
        self._log(f"Waiting {self._animation_delay}ms for animation...")
        time.sleep(self._animation_delay / 1000.0)
        
        # 4. Make sure window is still in front before capture
        self._bring_window_to_front()
        time.sleep(0.1)
        
        # 5. Capture log region
        log_image = screen_capture.capture_region(
            log_roi[0], log_roi[1], log_roi[2], log_roi[3]
        )
        
        # 6. Process with OCR
        result: ParseResult = ocr_processor.process_log_region(
            log_image, 
            mode="stat",
            threshold=config.ocr_threshold,
            psm=config.tesseract_psm
        )
        
        # Truncate long raw text for logging
        raw_text_short = result.raw_text[:150] + "..." if len(result.raw_text) > 150 else result.raw_text
        self._log(f"OCR Result: {result.result_type} - {raw_text_short}")
        
        # 7. Update iteration count
        iterations = self.status.iterations + 1
        self._update_status(iterations=iterations)
        
        # 6. Parse result
        if result.success:
            if result.result_type == "stat":
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
                    message=f"Current: {stat_value:.2f} (Best: {self._best_stat:.2f})"
                )
                self._log(f"Stat detected: {stat_value:.2f}")
                
                # Check if target reached
                if stat_value >= self._target_threshold:
                    return True
                    
            elif result.result_type == "failed":
                self._consecutive_failures += 1
                self._update_status(
                    failures=self._consecutive_failures,
                    message=f"Upgrade failed ({self._consecutive_failures} consecutive)"
                )
                self._log(f"Upgrade failed ({self._consecutive_failures} consecutive)")
        else:
            self._log(f"Failed to parse result: {result.error}")
        
        return False
    
    def _extract_stat_value(self, value_data: Dict[str, Any]) -> float:
        """
        Extract the current stat value from parsed data.
        
        Args:
            value_data: Parsed stat data from OCR
            
        Returns:
            Float value of the current stat
        """
        # Range format: [(82.9%~98.6%) -> (81.6%~97.1%)]
        if 'new_avg' in value_data:
            return value_data['new_avg']
        
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
