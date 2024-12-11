# Trash-Compactor
A utility for intelligent file compression on Windows 10/11 systems using the built-in NTFS compression algorithms and Windows' built-in "compact.exe" utility. Unlike [CompactGUI](https://github.com/IridiumIO/CompactGUI) (another tool that is based on compact.exe and primarily designed for compressing Steam games), this utility automatically selects the optimal compression algorithm based on file size - this lets you squeeze the most out of the compression algorithms and get even smaller file sizes, all while avoiding unnecessary compression, keeping things DRY (also known as "Don't Repeat Yourself").

## Features

- Automated compression using Windows NTFS compression
- Smart algorithm selection based on file size
- Skips poorly-compressed file formats (zip, media files, etc.)
- Skips already-compressed files (which compact.exe has already compressed)
- Detailed compression statistics

## Requirements

- Windows 10/11
- Administrator privileges

## Installation

### Option 1: Using the Executable (Recommended)

1. [Download the latest release](https://github.com/misha1350/trash-compactor/releases/latest)
2. Open PowerShell as Administrator:
    - Right-click Start Menu
    - Select "Windows PowerShell (Admin)" or "Windows Terminal (Admin)"
3. Drag the downloaded file into the PowerShell window, or navigate to the folder that contains the downloaded app:
    ```powershell
    cd path\to\downloads
    ```
4. Run the executable:
    ```powershell
    .\trash-compactor.exe
    ```
    Verbose output:
    ```powershell
    .\trash-compactor.exe -v
    ```

### Option 2: Running from Source

1. Open PowerShell as Administrator
2. Clone and navigate to the repository:
    ```powershell
    git clone https://github.com/misha1350/trash-compactor.git
    cd trash-compactor
    ```
3. Run the program:
    ```powershell
    python main.py
    ```

Note: For Option 2, ensure Git and Python 3.8+ are installed on your system.

Optional: you can compile the app yourself as I did, using PyInstaller:
    ```
    python -m PyInstaller --onefile --name trash-compactor --uac-admin main.py 
    ```

## Usage

1. Run the program as Administrator.
2. Enter the directory path you want to compress.
3. The program will automatically:
    - Scan all files recursively
    - Skip incompatible files
    - Apply optimal compression algorithms
    - Display compression statistics

## Development

To contribute to this project:

1. Fork the repository.
2. Create a new branch for your feature.
3. Submit a pull request.

## To-Do

### Immediate Priorities (v0.2.x)
- Bring back the simple weak CPU core count check (to disable LZX automatically if run on a potato)
- Fix incorrect reporting of how much space was saved after compression
- Improve weak hardware detection
- Replace `compact.exe` calls with direct Windows API calls:
  - Use `FSCTL_SET_COMPRESSION` via `DeviceIoControl` for compression
  - Use `GetFileAttributes()` to check compression state
  - Remove subprocess spawning overhead
- Add process priority management based on CPU core count
- Replace generic exception handling with specific error cases

### Short-term Goals (v0.3.0)
- Implement batch compression for multiple files or directories:
  - Group files by target compression algorithm
  - Process groups in parallel using worker threads
  - Balance thread count based on CPU cores
- Improve system directory exclusion (with configurable rules)
- Implement Chromium cache directory detection to avoid compressing already compressed cache files, in order to:
  - Exclude `*\Cache\Cache_Data\` directory compression (of Chromium-based web browsers and Electron apps)
  - Exclude Telegram's `\tdata\user_data\cache` and `\tdata\user_data\media_cache` compression
  - Exclude Microsoft Teams' `\LocalCache\Microsoft\MSTeams\*` compression
  - Exclude other most popular web browsers' cache directories compression
- Implement checking the compression status of the poorly compressed files in parallel (to make use of other cores)
- Log this in the "info" channel to notify the user (me) about such files
- Add basic test suite for core functionality
  - Implement a single-thread benchmark for checking if the CPU is fast enough to use LZX compression (not an Intel Atom with numerous, but weak cores)
  - Test compression detection accuracy
  - Verify API calls work correctly
  - Check error handling paths

### Long-term Goals (v0.x.x)
- Create a 1-click/unattended mode of operation
  - Automatically discover large folders (replacing WizTree and having to manually scour through folders)
  - Avoiding compressing specific folders, such as ones mentioned in short-term goals
  - Make life easier for The Greatest Technicians That Have Ever Lived
- Implement smart compression detection:
  - Use entropy analysis for compressibility estimation
  - Sample data chunks strategically
  - Cache results per file type
- Quality of Life features
  - More coloured output
  - Saving user configuration with an optional `.ini` file
- Research advanced compression methods:
  - Evaluate alternative NTFS compression APIs, like [UPX](https://github.com/upx/upx)
  - Consider filesystem-agnostic approaches (moving compressed files in/out of the source drive unpacks them)
  - Benchmark different compression strategies
  - Do something about it
