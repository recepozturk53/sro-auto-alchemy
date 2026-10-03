"""
Entry point for Silkroad Online Auto-Alchemy Bot.
Initializes logging and starts the main application.
"""

import sys
import os
import logging
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from src.gui.main_window import MainWindow


def setup_logging():
    """Configure logging for the application."""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "bot.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def check_dependencies():
    """Check if required dependencies are available."""
    missing = []
    
    try:
        import customtkinter
    except ImportError:
        missing.append("customtkinter")
    
    try:
        import mss
    except ImportError:
        missing.append("mss")
    
    try:
        import pytesseract
    except ImportError:
        missing.append("pytesseract")
    
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    
    if missing:
        print("ERROR: Missing required dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    
    # Check Tesseract installation. ocr.py also probes the common install paths
    # and honours the TESSERACT_CMD environment variable at runtime.
    try:
        version = pytesseract.get_tesseract_version()
        print(f"Tesseract OCR detected: {version}")
    except Exception as e:
        print("WARNING: Tesseract OCR engine not found.")
        print("Install it from: https://github.com/UB-Mannheim/tesseract/wiki")
        print("or set the TESSERACT_CMD environment variable to tesseract.exe.")
        print(f"Error: {e}")
    
    return True


def is_admin() -> bool:
    """Whether the current process has Administrator privileges."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def main():
    """Main entry point."""
    print("=" * 50)
    print("Silkroad Online Auto-Alchemy Bot")
    print("=" * 50)
    print()

    if not is_admin():
        print("NOTE: Not running as Administrator.")
        print("      If SRO_Client runs elevated, Windows blocks synthetic mouse")
        print("      input and the fuse button will never be clicked.")
        print("      Restart this tool as Administrator if clicking fails.")
        print()
    
    # Setup logging
    setup_logging()
    logging.info("Application starting...")
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create and run main window
    try:
        app = MainWindow()
        logging.info("GUI initialized successfully")
        app.run()
    except Exception as e:
        logging.error(f"Application error: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        sys.exit(1)
    
    logging.info("Application closed")


if __name__ == "__main__":
    main()
