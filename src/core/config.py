"""
Configuration module for Silkroad Online Auto-Alchemy Bot.
Manages persistent settings for bot configuration.
"""

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional, Tuple
import threading


@dataclass
class BotConfig:
    """Configuration dataclass for bot settings."""
    # Fuse button coordinates
    fuse_button_x: int = 0
    fuse_button_y: int = 0
    
    # Log ROI (Region of Interest) - (x, y, width, height)
    log_roi_x: int = 0
    log_roi_y: int = 0
    log_roi_width: int = 300
    log_roi_height: int = 150
    
    # Mode settings
    mode: str = "plus"  # "plus" or "stat"
    
    # Plus mode settings
    target_plus: int = 10
    current_plus: int = 0
    
    # Stat mode settings
    target_stat_threshold: float = 100.0
    
    # Timing settings (milliseconds)
    animation_delay: int = 2500
    click_delay: int = 500
    
    # Sound settings
    sound_enabled: bool = True
    
    # Advanced OCR settings
    ocr_threshold: int = 150  # OpenCV threshold value
    tesseract_psm: int = 6    # Tesseract page segmentation mode


class ConfigManager:
    """
    Manages configuration persistence and thread-safe access.
    Saves/loads config from JSON file in user's AppData directory.
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
            self._config = BotConfig()
            self._config_lock = threading.RLock()
            self._config_path = self._get_config_path()
            self._initialized = True
            self.load()
    
    def _get_config_path(self) -> str:
        """Get the configuration file path in AppData."""
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        config_dir = os.path.join(appdata, 'SroAutoAlchemy')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'config.json')
    
    @property
    def config(self) -> BotConfig:
        """Thread-safe access to config."""
        with self._config_lock:
            return self._config
    
    def update(self, **kwargs) -> None:
        """Update configuration values."""
        with self._config_lock:
            for key, value in kwargs.items():
                if hasattr(self._config, key):
                    setattr(self._config, key, value)
            self.save()
    
    def save(self) -> None:
        """Save configuration to JSON file."""
        with self._config_lock:
            try:
                with open(self._config_path, 'w', encoding='utf-8') as f:
                    json.dump(asdict(self._config), f, indent=4)
            except Exception as e:
                print(f"Error saving config: {e}")
    
    def load(self) -> None:
        """Load configuration from JSON file."""
        with self._config_lock:
            try:
                if os.path.exists(self._config_path):
                    with open(self._config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for key, value in data.items():
                            if hasattr(self._config, key):
                                setattr(self._config, key, value)
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def reset(self) -> None:
        """Reset configuration to defaults."""
        with self._config_lock:
            self._config = BotConfig()
            self.save()
    
    def get_fuse_button(self) -> Tuple[int, int]:
        """Get fuse button coordinates."""
        with self._config_lock:
            return (self._config.fuse_button_x, self._config.fuse_button_y)
    
    def set_fuse_button(self, x: int, y: int) -> None:
        """Set fuse button coordinates."""
        self.update(fuse_button_x=x, fuse_button_y=y)
    
    def get_log_roi(self) -> Tuple[int, int, int, int]:
        """Get log ROI as (x, y, width, height)."""
        with self._config_lock:
            return (
                self._config.log_roi_x,
                self._config.log_roi_y,
                self._config.log_roi_width,
                self._config.log_roi_height
            )
    
    def set_log_roi(self, x: int, y: int, width: int, height: int) -> None:
        """Set log ROI coordinates."""
        self.update(
            log_roi_x=x,
            log_roi_y=y,
            log_roi_width=width,
            log_roi_height=height
        )
    
    def is_configured(self) -> bool:
        """Check if essential coordinates are configured."""
        with self._config_lock:
            return (
                self._config.fuse_button_x > 0 and
                self._config.fuse_button_y > 0 and
                self._config.log_roi_width > 0 and
                self._config.log_roi_height > 0
            )


# Global config instance
config_manager = ConfigManager()
