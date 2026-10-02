# Silkroad Online Auto-Alchemy Bot

An automated bot for Silkroad Online alchemy system with CustomTkinter GUI.

## Features

- **Plus Mode**: Automatically upgrades items and stops when target plus level is reached
- **Stat Mode**: Monitors stat upgrades and stops when target threshold is met
- **OCR-based Log Reading**: Uses Tesseract OCR with OpenCV preprocessing
- **CustomTkinter GUI**: Clean, modern dark theme interface
- **Configurable Settings**: Adjustable timing delays and thresholds
- **Sound Alarms**: Audio notifications on success or failure

## Requirements

- Python 3.9+
- Tesseract OCR (must be installed separately)

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Tesseract Installation

### Windows
1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to default location (usually `C:\Program Files\Tesseract-OCR`)
3. Add to PATH or configure in the application

### Linux
```bash
sudo apt-get install tesseract-ocr
```

### macOS
```bash
brew install tesseract
```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```

2. **Configure Coordinates**:
   - Click "Pick Fuse Button" and click on the game's upgrade button
   - Click "Select Log Area" and drag to select the log region in the game

3. **Set Mode**:
   - **Plus Mode**: Set your target plus level (e.g., +10)
   - **Stat Mode**: Set your target stat threshold (e.g., 100.0)

4. **Adjust Timing** (optional):
   - Animation Delay: Time to wait after clicking for game animation (default: 1500ms)
   - Click Delay: Time between consecutive clicks (default: 300ms)

5. Click **Start** to begin the bot

## Modes Explained

### Plus Mode
- Reads plus levels from game log (+1, +2, etc.)
- Stops when current plus ≥ target plus
- Plays success alarm on completion
- Stops with failure alarm after too many consecutive failures

### Stat Mode
- Parses stat values from formats:
  - Simple: `[12.2->12.4]`
  - Range: `[(82.9%~98.6%) -> (81.6%~97.1%)]`
- Stops when current stat ≥ target threshold
- Tracks best/worst stat values encountered

## Building Executable

To create a standalone .exe file:

```bash
pyinstaller sro_alchemy_bot.spec
```

The executable will be in the `dist/` folder.

## Configuration

Configuration is automatically saved to:
- Windows: `%APPDATA%\SroAutoAlchemy\config.json`

## Disclaimer

This tool is for educational purposes only. Use at your own risk. Automating game actions may violate the game's Terms of Service.

## License

MIT License
