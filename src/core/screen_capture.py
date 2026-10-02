"""
Screen capture module using mss for fast screen capture.
Provides functionality to capture specific regions of the screen.
"""

import mss
import numpy as np
from typing import Tuple, Optional
from PIL import Image
import threading


class ScreenCapture:
    """
    Screen capture utility using mss for fast performance.
    Thread-safe implementation for use in background threads.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._sct = mss.mss()
            self._capture_lock = threading.RLock()
            self._initialized = True
    
    def capture_region(self, x: int, y: int, width: int, height: int) -> np.ndarray:
        """
        Capture a specific region of the screen.
        
        Args:
            x: X coordinate of the region
            y: Y coordinate of the region
            width: Width of the region
            height: Height of the region
            
        Returns:
            numpy array (BGR format) of the captured region
        """
        with self._capture_lock:
            monitor = {
                "left": int(x),
                "top": int(y),
                "width": int(width),
                "height": int(height)
            }
            
            # Capture the region
            screenshot = self._sct.grab(monitor)
            
            # Convert to numpy array (BGRA -> BGR)
            img = np.array(screenshot)
            img = img[:, :, :3]  # Remove alpha channel
            
            return img
    
    def capture_full_screen(self, monitor_index: int = 0) -> np.ndarray:
        """
        Capture the full screen.
        
        Args:
            monitor_index: Index of the monitor to capture (0 = primary)
            
        Returns:
            numpy array (BGR format) of the captured screen
        """
        with self._capture_lock:
            monitor = self._sct.monitors[monitor_index + 1]  # Index 0 is all monitors combined
            screenshot = self._sct.grab(monitor)
            img = np.array(screenshot)
            img = img[:, :, :3]
            return img
    
    def capture_region_as_pil(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """
        Capture a region and return as PIL Image.
        
        Args:
            x: X coordinate of the region
            y: Y coordinate of the region
            width: Width of the region
            height: Height of the region
            
        Returns:
            PIL Image object (RGB format)
        """
        img_array = self.capture_region(x, y, width, height)
        # Convert BGR to RGB for PIL
        img_rgb = img_array[:, :, ::-1]
        return Image.fromarray(img_rgb)
    
    def get_screen_size(self, monitor_index: int = 0) -> Tuple[int, int]:
        """
        Get the screen size.
        
        Args:
            monitor_index: Index of the monitor (0 = primary)
            
        Returns:
            Tuple of (width, height)
        """
        monitor = self._sct.monitors[monitor_index + 1]
        return (monitor["width"], monitor["height"])
    
    def save_capture(self, x: int, y: int, width: int, height: int, filepath: str) -> bool:
        """
        Capture a region and save to file.
        
        Args:
            x: X coordinate
            y: Y coordinate
            width: Width of region
            height: Height of region
            filepath: Path to save the image
            
        Returns:
            True if successful, False otherwise
        """
        try:
            img = self.capture_region_as_pil(x, y, width, height)
            img.save(filepath)
            return True
        except Exception as e:
            print(f"Error saving capture: {e}")
            return False
    
    def close(self):
        """Close the mss instance."""
        with self._capture_lock:
            if self._sct:
                self._sct.close()


# Global instance
screen_capture = ScreenCapture()
