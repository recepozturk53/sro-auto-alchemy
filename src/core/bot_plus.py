"""
Plus Mode bot implementation.
Clicks upgrade button, waits for animation, reads log for plus levels.
Stops when current_plus >= target_plus.
"""

import time
from typing import Optional
from .bot_base import BotBase, BotState, StopReason
from .config import config_manager


class PlusModeBot(BotBase):
    """
    Bot for Plus upgrade mode.
    Reads plus levels from game log and stops when target is reached.
    """
    
    def __init__(self):
        super().__init__()
        self._current_plus = 0
        self._target_plus = 10
        self._consecutive_failures = 0
        self._max_failures = 10  # Stop after this many consecutive failures
    
    def configure(
        self, 
        target_plus: int,
        animation_delay: int = 1500,
        click_delay: int = 300,
        max_failures: int = 10
    ) -> None:
        """
        Configure the Plus mode bot.
        
        Args:
            target_plus: Target plus level to reach
            animation_delay: Delay after clicking (ms)
            click_delay: Delay between clicks (ms)
            max_failures: Maximum consecutive failures before stopping
        """
        self._target_plus = target_plus
        self._animation_delay = animation_delay
        self._click_delay = click_delay
        self._max_failures = max_failures
        
        self._update_status(
            target_value=float(target_plus),
            message=f"Configured: Target +{target_plus}"
        )
        self._log(f"Plus mode configured: Target +{target_plus}")
    
    def _run_loop(self) -> None:
        """Main bot loop for Plus mode."""
        self._log("Plus mode loop started")
        self._current_plus = 0
        self._consecutive_failures = 0
        
        # Get configuration
        config = config_manager.config
        fuse_x, fuse_y = config_manager.get_fuse_button()
        log_roi = config_manager.get_log_roi()
        
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
                        message=f"Target +{self._target_plus} reached!",
                        stop_reason=StopReason.TARGET_REACHED
                    )
                    self._log(f"SUCCESS: Target +{self._target_plus} reached!")
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
        result = self._fuse_and_wait("plus")
        if result is None:
            return False  # Stopped by user or click blocked

        # Update iteration count
        iterations = self.status.iterations + 1
        self._update_status(iterations=iterations)
        
        # Parse result
        if result.success:
            if result.result_type == "plus":
                plus_level = result.value
                self._current_plus = plus_level
                self._consecutive_failures = 0
                
                self._update_status(
                    current_value=float(plus_level),
                    failures=0,
                    message=f"Current: +{plus_level}"
                )
                self._log(f"Plus level detected: +{plus_level}")
                
                # Check if target reached
                if plus_level >= self._target_plus:
                    return True
                    
            elif result.result_type == "failed":
                self._consecutive_failures += 1
                self._update_status(
                    failures=self._consecutive_failures,
                    message=f"Upgrade failed ({self._consecutive_failures} consecutive)"
                )
                self._log(f"Upgrade failed ({self._consecutive_failures} consecutive)")
                
                # Reset current plus tracking on failure (depends on game mechanics)
                # In Silkroad, failure may reset to lower level or stay same
                # We don't reset _current_plus here as OCR will read actual level
        else:
            self._log(f"Failed to parse result: {result.error}")
        
        return False
    
    def get_current_plus(self) -> int:
        """Get the current detected plus level."""
        return self._current_plus
    
    def get_consecutive_failures(self) -> int:
        """Get the count of consecutive failures."""
        return self._consecutive_failures
