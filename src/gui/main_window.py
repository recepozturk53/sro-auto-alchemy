"""
Main CustomTkinter GUI for Silkroad Online Auto-Alchemy Bot.
Provides a clean, minimalist interface for bot control.
"""

import customtkinter as ctk
from dataclasses import replace
from typing import Optional
import queue
import threading
import time

from ..core.config import config_manager, BotConfig
from ..core.bot_plus import PlusModeBot
from ..core.bot_stat import StatModeBot
from ..core.bot_base import BotState, BotStatus
from ..core.screen_capture import screen_capture
from ..core.ocr import ocr_processor
from .coordinate_picker import SelectionHelper

# How often the Tk main thread applies UI updates queued by the bot thread
UI_POLL_MS = 50


class MainWindow:
    """
    Main application window using CustomTkinter.
    Clean, minimalist design with tabbed interface for modes.
    """
    
    def __init__(self):
        # Initialize CTk
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        
        # Create main window
        self.root = ctk.CTk()
        self.root.title("SRO Auto-Alchemy Bot")
        self.root.geometry("500x720")
        self.root.resizable(False, False)
        
        # Initialize components
        self._ui_queue: "queue.Queue" = queue.Queue()
        self._selection_helper = SelectionHelper()
        self._plus_bot: Optional[PlusModeBot] = None
        self._stat_bot: Optional[StatModeBot] = None
        self._current_mode = "plus"
        
        # Build UI
        self._create_widgets()
        self._load_config()
        self._setup_bots()
    
    def _create_widgets(self) -> None:
        """Create all GUI widgets."""
        # Main container
        self._main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self._main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Title
        self._title_label = ctk.CTkLabel(
            self._main_frame,
            text="Silkroad Online Auto-Alchemy Bot",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self._title_label.pack(pady=(0, 15))
        
        # Mode selector
        self._create_mode_selector()
        
        # Settings section
        self._create_settings_section()
        
        # Coordinate picker section
        self._create_coordinate_section()
        
        # Control section
        self._create_control_section()
        
        # Status section
        self._create_status_section()
        
        # Log section
        self._create_log_section()
    
    def _create_mode_selector(self) -> None:
        """Create mode selection tabs."""
        self._mode_frame = ctk.CTkFrame(self._main_frame)
        self._mode_frame.pack(fill="x", pady=(0, 10))
        
        self._mode_var = ctk.StringVar(value="plus")
        
        self._plus_radio = ctk.CTkRadioButton(
            self._mode_frame,
            text="Plus Mode",
            variable=self._mode_var,
            value="plus",
            command=self._on_mode_change
        )
        self._plus_radio.pack(side="left", padx=20, pady=10)
        
        self._stat_radio = ctk.CTkRadioButton(
            self._mode_frame,
            text="Stat Mode",
            variable=self._mode_var,
            value="stat",
            command=self._on_mode_change
        )
        self._stat_radio.pack(side="left", padx=20, pady=10)
    
    def _create_settings_section(self) -> None:
        """Create settings input section."""
        self._settings_frame = ctk.CTkFrame(self._main_frame)
        self._settings_frame.pack(fill="x", pady=(0, 10))
        
        # Plus mode settings
        self._plus_settings_frame = ctk.CTkFrame(self._settings_frame, fg_color="transparent")
        self._plus_settings_frame.pack(fill="x", padx=10, pady=10)
        
        self._target_plus_label = ctk.CTkLabel(
            self._plus_settings_frame,
            text="Target Plus Level:",
            font=ctk.CTkFont(size=12)
        )
        self._target_plus_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        
        self._target_plus_entry = ctk.CTkEntry(
            self._plus_settings_frame,
            width=100,
            placeholder_text="10"
        )
        self._target_plus_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self._target_plus_entry.insert(0, "10")
        
        # Stat mode settings (hidden by default)
        self._stat_settings_frame = ctk.CTkFrame(self._settings_frame, fg_color="transparent")
        
        self._target_stat_label = ctk.CTkLabel(
            self._stat_settings_frame,
            text="Target Stat Threshold:",
            font=ctk.CTkFont(size=12)
        )
        self._target_stat_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        
        self._target_stat_entry = ctk.CTkEntry(
            self._stat_settings_frame,
            width=100,
            placeholder_text="100.0"
        )
        self._target_stat_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self._target_stat_entry.insert(0, "100.0")
        
        # Timing settings
        self._timing_frame = ctk.CTkFrame(self._settings_frame, fg_color="transparent")
        self._timing_frame.pack(fill="x", padx=10, pady=5)
        
        self._animation_delay_label = ctk.CTkLabel(
            self._timing_frame,
            text="Animation Delay (ms):",
            font=ctk.CTkFont(size=11)
        )
        self._animation_delay_label.grid(row=0, column=0, sticky="w", padx=5, pady=3)
        
        self._animation_delay_entry = ctk.CTkEntry(
            self._timing_frame,
            width=80,
            placeholder_text="2500"
        )
        self._animation_delay_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        self._animation_delay_entry.insert(0, "2500")
        
        self._click_delay_label = ctk.CTkLabel(
            self._timing_frame,
            text="Click Delay (ms):",
            font=ctk.CTkFont(size=11)
        )
        self._click_delay_label.grid(row=0, column=2, sticky="w", padx=15, pady=3)
        
        self._click_delay_entry = ctk.CTkEntry(
            self._timing_frame,
            width=80,
            placeholder_text="300"
        )
        self._click_delay_entry.grid(row=0, column=3, sticky="w", padx=5, pady=3)
        self._click_delay_entry.insert(0, "300")
    
    def _create_coordinate_section(self) -> None:
        """Create coordinate picker section."""
        self._coord_frame = ctk.CTkFrame(self._main_frame)
        self._coord_frame.pack(fill="x", pady=(0, 10))
        
        self._coord_label = ctk.CTkLabel(
            self._coord_frame,
            text="Coordinate Setup",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self._coord_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Fuse button
        self._fuse_frame = ctk.CTkFrame(self._coord_frame, fg_color="transparent")
        self._fuse_frame.pack(fill="x", padx=10, pady=5)
        
        self._pick_fuse_btn = ctk.CTkButton(
            self._fuse_frame,
            text="Pick Fuse Button",
            width=120,
            command=self._pick_fuse_button
        )
        self._pick_fuse_btn.pack(side="left", padx=5)
        
        self._fuse_label = ctk.CTkLabel(
            self._fuse_frame,
            text="Not set",
            font=ctk.CTkFont(size=11)
        )
        self._fuse_label.pack(side="left", padx=10)
        
        # Log ROI
        self._roi_frame = ctk.CTkFrame(self._coord_frame, fg_color="transparent")
        self._roi_frame.pack(fill="x", padx=10, pady=5)
        
        self._pick_roi_btn = ctk.CTkButton(
            self._roi_frame,
            text="Select Log Area",
            width=120,
            command=self._pick_log_roi
        )
        self._pick_roi_btn.pack(side="left", padx=5)
        
        self._roi_label = ctk.CTkLabel(
            self._roi_frame,
            text="Not set",
            font=ctk.CTkFont(size=11)
        )
        self._roi_label.pack(side="left", padx=10)
        
        # Test OCR button
        self._test_frame = ctk.CTkFrame(self._coord_frame, fg_color="transparent")
        self._test_frame.pack(fill="x", padx=10, pady=5)
        
        self._test_ocr_btn = ctk.CTkButton(
            self._test_frame,
            text="Test OCR",
            width=120,
            fg_color="purple",
            hover_color="darkorchid",
            command=self._test_ocr
        )
        self._test_ocr_btn.pack(side="left", padx=5)
        
        self._test_label = ctk.CTkLabel(
            self._test_frame,
            text="Click to test OCR on selected region",
            font=ctk.CTkFont(size=11)
        )
        self._test_label.pack(side="left", padx=10)
    
    def _create_control_section(self) -> None:
        """Create bot control buttons."""
        self._control_frame = ctk.CTkFrame(self._main_frame)
        self._control_frame.pack(fill="x", pady=(0, 10))
        
        self._start_btn = ctk.CTkButton(
            self._control_frame,
            text="▶ Start",
            width=100,
            fg_color="green",
            hover_color="darkgreen",
            command=self._start_bot
        )
        self._start_btn.pack(side="left", padx=15, pady=15)
        
        self._pause_btn = ctk.CTkButton(
            self._control_frame,
            text="⏸ Pause",
            width=100,
            fg_color="orange",
            hover_color="darkorange",
            command=self._pause_bot,
            state="disabled"
        )
        self._pause_btn.pack(side="left", padx=15, pady=15)
        
        self._stop_btn = ctk.CTkButton(
            self._control_frame,
            text="⏹ Stop",
            width=100,
            fg_color="red",
            hover_color="darkred",
            command=self._stop_bot,
            state="disabled"
        )
        self._stop_btn.pack(side="left", padx=15, pady=15)
    
    def _create_status_section(self) -> None:
        """Create status display section."""
        self._status_frame = ctk.CTkFrame(self._main_frame)
        self._status_frame.pack(fill="x", pady=(0, 10))
        
        self._status_label_title = ctk.CTkLabel(
            self._status_frame,
            text="Status",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self._status_label_title.pack(anchor="w", padx=10, pady=(10, 5))
        
        self._status_text = ctk.CTkLabel(
            self._status_frame,
            text="Idle",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self._status_text.pack(anchor="w", padx=10, pady=5)
        
        # Progress indicators
        self._progress_frame = ctk.CTkFrame(self._status_frame, fg_color="transparent")
        self._progress_frame.pack(fill="x", padx=10, pady=5)
        
        self._current_label = ctk.CTkLabel(
            self._progress_frame,
            text="Current: --",
            font=ctk.CTkFont(size=11)
        )
        self._current_label.pack(side="left", padx=5)
        
        self._target_label = ctk.CTkLabel(
            self._progress_frame,
            text="Target: --",
            font=ctk.CTkFont(size=11)
        )
        self._target_label.pack(side="left", padx=15)
        
        self._iterations_label = ctk.CTkLabel(
            self._progress_frame,
            text="Iterations: 0",
            font=ctk.CTkFont(size=11)
        )
        self._iterations_label.pack(side="left", padx=15)
    
    def _create_log_section(self) -> None:
        """Create log display section."""
        self._log_frame = ctk.CTkFrame(self._main_frame)
        self._log_frame.pack(fill="both", expand=True, pady=(0, 5))
        
        self._log_label = ctk.CTkLabel(
            self._log_frame,
            text="Log",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self._log_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self._log_textbox = ctk.CTkTextbox(
            self._log_frame,
            height=120,
            font=ctk.CTkFont(size=10)
        )
        self._log_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._log_textbox.configure(state="disabled")
    
    def _setup_bots(self) -> None:
        """Initialize bot instances."""
        self._plus_bot = PlusModeBot()
        self._stat_bot = StatModeBot()
        
        # Set callbacks
        # Bot callbacks run on the bot thread; they only enqueue (see _post_ui)
        self._plus_bot.set_callbacks(
            on_status_change=lambda status: self._post_ui(
                self._on_status_change, replace(status)
            ),
            on_log=lambda message: self._post_ui(self._on_log, message)
        )
        self._stat_bot.set_callbacks(
            on_status_change=lambda status: self._post_ui(
                self._on_status_change, replace(status)
            ),
            on_log=lambda message: self._post_ui(self._on_log, message)
        )

    def _post_ui(self, func, *args) -> None:
        """
        Run a UI update on the Tk main thread.

        Tk widgets must never be touched from the bot thread: when the main
        thread is blocked in bot.stop() -> join(), a Tk call from the bot
        thread waits for the main thread and both deadlock. Calls made on the
        main thread run immediately; others are queued for _drain_ui_queue.
        """
        if threading.current_thread() is threading.main_thread():
            func(*args)
        else:
            self._ui_queue.put((func, args))

    def _drain_ui_queue(self) -> None:
        """Apply queued UI updates (main thread), then poll again."""
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception as e:
                    print(f"UI update error: {e}")
        except queue.Empty:
            pass
        self.root.after(UI_POLL_MS, self._drain_ui_queue)
    
    def _load_config(self) -> None:
        """Load configuration and update UI."""
        config = config_manager.config
        
        # Update coordinate labels
        if config.fuse_button_x > 0 and config.fuse_button_y > 0:
            self._fuse_label.configure(text=f"({config.fuse_button_x}, {config.fuse_button_y})")
        
        if config.log_roi_width > 0 and config.log_roi_height > 0:
            self._roi_label.configure(
                text=f"({config.log_roi_x}, {config.log_roi_y}) {config.log_roi_width}x{config.log_roi_height}"
            )
        
        # Update timing
        self._animation_delay_entry.delete(0, "end")
        self._animation_delay_entry.insert(0, str(config.animation_delay))
        
        self._click_delay_entry.delete(0, "end")
        self._click_delay_entry.insert(0, str(config.click_delay))
    
    def _on_mode_change(self) -> None:
        """Handle mode change."""
        self._current_mode = self._mode_var.get()
        
        if self._current_mode == "plus":
            self._stat_settings_frame.pack_forget()
            self._plus_settings_frame.pack(fill="x", padx=10, pady=10)
        else:
            self._plus_settings_frame.pack_forget()
            self._stat_settings_frame.pack(fill="x", padx=10, pady=10)
    
    def _pick_fuse_button(self) -> None:
        """Open fuse button picker."""
        def on_selected(x: int, y: int):
            config_manager.set_fuse_button(x, y)
            self._fuse_label.configure(text=f"({x}, {y})")
            self._log_message(f"Fuse button set to: ({x}, {y})")
        
        self._selection_helper.pick_fuse_button(on_selected)
    
    def _pick_log_roi(self) -> None:
        """Open log ROI selector."""
        def on_selected(x: int, y: int, width: int, height: int):
            config_manager.set_log_roi(x, y, width, height)
            self._roi_label.configure(text=f"({x}, {y}) {width}x{height}")
            self._log_message(f"Log ROI set to: ({x}, {y}) {width}x{height}")
        
        self._selection_helper.pick_log_roi(on_selected)
    
    def _test_ocr(self) -> None:
        """Test OCR on selected log region."""
        config = config_manager.config
        log_roi = config_manager.get_log_roi()
        
        if log_roi[2] == 0 or log_roi[3] == 0:
            self._log_message("ERROR: Please select Log Area first!")
            return
        
        if ocr_processor.is_tesseract_available:
            self._log_message(f"Tesseract ready: {ocr_processor.tesseract_info()}")
        else:
            self._log_message(
                f"ERROR: Tesseract engine not found ({ocr_processor.tesseract_info()})"
            )

        self._log_message("Testing OCR... bringing the game window to the front")

        try:
            # The log area is usually covered by this window when the button
            # is pressed: show the game first, capture, then come back.
            if not self._stat_bot._bring_window_to_front():
                self._log_message("WARNING: game window could not be activated")
            time.sleep(0.4)
            log_image = screen_capture.capture_region(
                log_roi[0], log_roi[1], log_roi[2], log_roi[3]
            )
            self.root.lift()
            self.root.focus_force()

            # Save debug image
            import cv2
            debug_path = "debug_log_region.png"
            cv2.imwrite(debug_path, log_image)
            self._log_message(f"Debug image saved: {debug_path}")
            
            # Process with OCR
            result = ocr_processor.process_log_region(
                log_image,
                mode=self._current_mode,
                threshold=config.ocr_threshold,
                psm=config.tesseract_psm
            )
            
            # Show results
            self._log_message(f"OCR Raw Text: {result.raw_text}")
            self._log_message(f"Result Type: {result.result_type}")
            if result.success:
                self._log_message(f"Parsed Value: {result.value}")
            else:
                self._log_message(f"Error: {result.error}")
                
        except Exception as e:
            self._log_message(f"OCR Test Error: {e}")
    
    def _start_bot(self) -> None:
        """Start the bot."""
        if not config_manager.is_configured():
            self._log_message("ERROR: Please configure fuse button and log ROI first!")
            return
        
        # Get timing settings
        try:
            animation_delay = int(self._animation_delay_entry.get())
            click_delay = int(self._click_delay_entry.get())
        except ValueError:
            self._log_message("ERROR: Invalid timing values!")
            return
        
        # Configure and start appropriate bot
        if self._current_mode == "plus":
            try:
                target_plus = int(self._target_plus_entry.get())
            except ValueError:
                self._log_message("ERROR: Invalid target plus value!")
                return
            
            self._plus_bot.configure(
                target_plus=target_plus,
                animation_delay=animation_delay,
                click_delay=click_delay
            )
            self._plus_bot.start()
            self._target_label.configure(text=f"Target: +{target_plus}")
            
        else:  # stat mode
            try:
                target_stat = float(self._target_stat_entry.get())
            except ValueError:
                self._log_message("ERROR: Invalid target stat value!")
                return
            
            self._stat_bot.configure(
                target_threshold=target_stat,
                animation_delay=animation_delay,
                click_delay=click_delay
            )
            self._stat_bot.start()
            self._target_label.configure(text=f"Target: {target_stat}")
        
        # Update UI
        self._start_btn.configure(state="disabled")
        self._pause_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
    
    def _pause_bot(self) -> None:
        """Pause/resume the bot."""
        if self._current_mode == "plus":
            self._plus_bot.pause()
        else:
            self._stat_bot.pause()
    
    def _stop_bot(self) -> None:
        """Stop the bot."""
        if self._current_mode == "plus":
            self._plus_bot.stop()
        else:
            self._stat_bot.stop()
        
        # Update UI
        self._start_btn.configure(state="normal")
        self._pause_btn.configure(state="disabled", text="⏸ Pause")
        self._stop_btn.configure(state="disabled")
        self._status_text.configure(text="Stopped", text_color="red")
    
    def _on_status_change(self, status: BotStatus) -> None:
        """Handle bot status changes."""
        # Update status text
        self._status_text.configure(text=status.message)
        
        # Update status color based on state
        if status.state == BotState.RUNNING:
            self._status_text.configure(text_color="green")
        elif status.state == BotState.PAUSED:
            self._status_text.configure(text_color="orange")
        elif status.state == BotState.COMPLETED:
            self._status_text.configure(text_color="green")
            self._start_btn.configure(state="normal")
            self._pause_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")
        elif status.state == BotState.FAILED:
            self._status_text.configure(text_color="red")
            self._start_btn.configure(state="normal")
            self._pause_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")
        elif status.state == BotState.STOPPED:
            self._status_text.configure(text_color="gray")
            self._start_btn.configure(state="normal")
            self._pause_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")
        
        # Update progress labels
        if status.current_value is not None:
            self._current_label.configure(text=f"Current: {status.current_value:.1f}")
        
        self._iterations_label.configure(text=f"Iterations: {status.iterations}")
        
        # Update pause button text
        if status.state == BotState.PAUSED:
            self._pause_btn.configure(text="▶ Resume")
        elif status.state == BotState.RUNNING:
            self._pause_btn.configure(text="⏸ Pause")
    
    def _on_log(self, message: str) -> None:
        """Handle log messages from bot."""
        self._log_message(message)
    
    def _log_message(self, message: str) -> None:
        """Add message to log display."""
        self._log_textbox.configure(state="normal")
        self._log_textbox.insert("end", f"{message}\n")
        self._log_textbox.see("end")
        self._log_textbox.configure(state="disabled")
    
    def run(self) -> None:
        """Run the main application."""
        self.root.after(UI_POLL_MS, self._drain_ui_queue)
        self.root.mainloop()
