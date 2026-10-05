"""
Coordinate picker tool for selecting screen coordinates.
Provides two tools:
1. Click picker for fuse button coordinates
2. Drag selector for log ROI area
"""

import tkinter as tk
from tkinter import Canvas, Toplevel
from typing import Optional, Tuple, Callable
from PIL import ImageGrab, ImageTk, Image
import threading


class CoordinatePicker:
    """
    Tool for picking screen coordinates and regions.
    Opens a fullscreen transparent overlay for selection.
    """
    
    def __init__(self, on_complete: Callable[[Tuple[int, int]], None] = None):
        """
        Initialize coordinate picker.
        
        Args:
            on_complete: Callback when coordinate is selected (x, y)
        """
        self.on_complete = on_complete
        self._window: Optional[Toplevel] = None
        self._canvas: Optional[Canvas] = None
        self._selected_coords: Optional[Tuple[int, int]] = None
    
    def pick_point(self) -> None:
        """
        Open a fullscreen overlay to pick a single point.
        User clicks anywhere to select coordinates.
        """
        self._close_existing()
        
        # Create fullscreen window
        self._window = Toplevel()
        self._window.attributes('-fullscreen', True)
        self._window.attributes('-topmost', True)
        self._window.attributes('-alpha', 0.3)
        self._window.configure(bg='black', cursor='crosshair')
        
        # Get screen dimensions
        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()
        
        # Create canvas
        self._canvas = Canvas(
            self._window,
            width=screen_width,
            height=screen_height,
            bg='gray',
            highlightthickness=0
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        
        # Instructions
        self._canvas.create_text(
            screen_width // 2, 30,
            text="Click to select a point (Press ESC to cancel)",
            fill='white',
            font=('Arial', 16, 'bold')
        )
        
        # Bind events
        self._canvas.bind('<Button-1>', self._on_point_click)
        self._window.bind('<Escape>', lambda e: self._cancel())
        
        # Focus window
        self._window.focus_force()
    
    def _on_point_click(self, event) -> None:
        """Handle point selection click."""
        x = event.x_root
        y = event.y_root
        
        self._selected_coords = (x, y)
        
        # Show confirmation
        self._canvas.delete('all')
        self._canvas.create_oval(x - 10, y - 10, x + 10, y + 10, fill='red', outline='white', width=2)
        self._canvas.create_text(
            x, y + 30,
            text=f"Selected: ({x}, {y})",
            fill='white',
            font=('Arial', 12, 'bold')
        )
        
        # Close after short delay
        self._window.after(500, lambda: self._complete_point(x, y))
    
    def _complete_point(self, x: int, y: int) -> None:
        """Complete point selection and close."""
        self._close_existing()
        
        if self.on_complete:
            self.on_complete((x, y))
    
    def _cancel(self) -> None:
        """Cancel selection."""
        self._close_existing()
    
    def _close_existing(self) -> None:
        """Close existing window if open."""
        if self._window:
            try:
                self._window.destroy()
            except:
                pass
            self._window = None
            self._canvas = None


class RegionSelector:
    """
    Tool for selecting a rectangular region on screen.
    User clicks and drags to define the region.
    """
    
    def __init__(self, on_complete: Callable[[Tuple[int, int, int, int]], None] = None,
                 on_cancel: Optional[Callable[[], None]] = None):
        """
        Initialize region selector.
        
        Args:
            on_complete: Callback when region is selected (x, y, width, height)
        """
        self.on_complete = on_complete
        self.on_cancel = on_cancel
        self._window: Optional[Toplevel] = None
        self._canvas: Optional[Canvas] = None
        self._start_x: int = 0
        self._start_y: int = 0
        self._current_rect = None
        self._screenshot: Optional[ImageTk.PhotoImage] = None
    
    def select_region(self, prepare_capture: Optional[Callable[[], None]] = None,
                      label: str = "Log Region") -> None:
        """
        Open a fullscreen overlay to select a rectangular region.
        User clicks and drags to define the area.
        """
        self._close_existing()
        
        # Take screenshot first
        if prepare_capture:
            prepare_capture()
        screenshot = ImageGrab.grab()
        
        # Create fullscreen window
        self._window = Toplevel()
        self._window.attributes('-fullscreen', True)
        self._window.attributes('-topmost', True)
        self._window.overrideredirect(True)
        self._window.configure(cursor='crosshair')
        
        # Get screen dimensions
        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()
        
        # Create canvas with screenshot
        self._canvas = Canvas(
            self._window,
            width=screen_width,
            height=screen_height,
            highlightthickness=0
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        
        # Display screenshot
        self._screenshot = ImageTk.PhotoImage(screenshot)
        self._canvas.create_image(0, 0, anchor=tk.NW, image=self._screenshot)
        
        # Overlay with semi-transparent effect
        self._canvas.create_rectangle(
            0, 0, screen_width, screen_height,
            fill='gray',
            stipple='gray50'
        )
        
        # Instructions
        self._canvas.create_text(
            screen_width // 2, 30,
            text=f"Click and drag to select the {label} (Press ESC to cancel)",
            fill='white',
            font=('Arial', 16, 'bold')
        )
        
        # Bind events
        self._canvas.bind('<Button-1>', self._on_drag_start)
        self._canvas.bind('<B1-Motion>', self._on_drag_motion)
        self._canvas.bind('<ButtonRelease-1>', self._on_drag_release)
        self._window.bind('<Escape>', lambda e: self._cancel())
        
        # Focus window
        self._window.focus_force()
    
    def _on_drag_start(self, event) -> None:
        """Handle drag start."""
        self._start_x = event.x
        self._start_y = event.y
    
    def _on_drag_motion(self, event) -> None:
        """Handle drag motion - update rectangle preview."""
        if self._current_rect:
            self._canvas.delete(self._current_rect)
        
        self._current_rect = self._canvas.create_rectangle(
            self._start_x, self._start_y, event.x, event.y,
            outline='red',
            width=2,
            fill='',
            dash=(4, 4)
        )
    
    def _on_drag_release(self, event) -> None:
        """Handle drag release - complete selection."""
        end_x = event.x
        end_y = event.y
        
        # Normalize coordinates
        x1 = min(self._start_x, end_x)
        y1 = min(self._start_y, end_y)
        x2 = max(self._start_x, end_x)
        y2 = max(self._start_y, end_y)
        
        width = x2 - x1
        height = y2 - y1
        
        # Minimum size check
        if width < 10 or height < 10:
            self._cancel()
            return
        
        # Show confirmation
        if self._current_rect:
            self._canvas.delete(self._current_rect)
        
        self._canvas.create_rectangle(
            x1, y1, x2, y2,
            outline='green',
            width=3
        )
        
        self._canvas.create_text(
            (x1 + x2) // 2, y2 + 20,
            text=f"Region: ({x1}, {y1}) {width}x{height}",
            fill='white',
            font=('Arial', 12, 'bold')
        )
        
        # Close after short delay
        self._window.after(800, lambda: self._complete_region(x1, y1, width, height))
    
    def _complete_region(self, x: int, y: int, width: int, height: int) -> None:
        """Complete region selection and close."""
        self._close_existing()
        
        if self.on_complete:
            self.on_complete((x, y, width, height))
    
    def _cancel(self) -> None:
        """Cancel selection."""
        self._close_existing()
        if self.on_cancel:
            self.on_cancel()
    
    def _close_existing(self) -> None:
        """Close existing window if open."""
        if self._window:
            try:
                self._window.destroy()
            except:
                pass
            self._window = None
            self._canvas = None
            self._screenshot = None
            self._current_rect = None


class SelectionHelper:
    """
    Helper class to coordinate picking fuse button and log ROI.
    Provides a simple interface for the GUI.
    """
    
    def __init__(self):
        self._point_picker: Optional[CoordinatePicker] = None
        self._region_selector: Optional[RegionSelector] = None
    
    def pick_fuse_button(self, callback: Callable[[int, int], None]) -> None:
        """
        Pick fuse button coordinates.
        
        Args:
            callback: Callback receiving (x, y) coordinates
        """
        def on_point_selected(coords: Tuple[int, int]):
            callback(coords[0], coords[1])
        
        self._point_picker = CoordinatePicker(on_complete=on_point_selected)
        self._point_picker.pick_point()
    
    def pick_log_roi(self, callback: Callable[[int, int, int, int], None]) -> None:
        """
        Pick log region ROI.
        
        Args:
            callback: Callback receiving (x, y, width, height)
        """
        def on_region_selected(region: Tuple[int, int, int, int]):
            callback(region[0], region[1], region[2], region[3])
        
        self._region_selector = RegionSelector(on_complete=on_region_selected)
        self._region_selector.select_region()

    def pick_item_hover(self, callback: Callable[[int, int], None]) -> None:
        """Pick the screen point over the item whose tooltip is read."""
        self.pick_fuse_button(callback)

    def pick_percent_roi(self, callback: Callable[[int, int, int, int], None],
                         on_cancel: Optional[Callable[[], None]] = None) -> None:
        """Freeze the manually hovered tooltip before showing the overlay."""
        def on_region_selected(region: Tuple[int, int, int, int]):
            callback(*region)

        self._region_selector = RegionSelector(on_complete=on_region_selected,
                                               on_cancel=on_cancel)
        self._region_selector.select_region(label="Percentage")
    
    def close_all(self) -> None:
        """Close all open pickers."""
        if self._point_picker:
            self._point_picker._close_existing()
        if self._region_selector:
            self._region_selector._close_existing()
