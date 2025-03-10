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
- Display a warning message if the directory that is being compressed is on an HDD instead of an SSD, eMMC storage, or an SD card, because HDDs can suffer from fragmentation and this will drastically decrease hard drive performance
  - Tell user to go buy an SSD and clone the hard drive or make a clean install of the system
- Replace `compact.exe` calls with direct Windows API calls:
  - Use `FSCTL_SET_COMPRESSION` via `DeviceIoControl` for compression
  - Use `GetFileAttributes()` to check compression state
  - Remove subprocess spawning overhead

### Short-term Goals (v0.3.0)
- UI overhaul: 
  - Create a progress bar (with .01% precision) at the bottom of the terminal window, tied to the amount of processed files relative to total files
  - Put the silent output behind a feature flag (progress bar has to be enabled all the time)
  - Close the terminal after finishing compression only after pressing "Q" once or "Esc" twice
  - Count and display estimated time to completion based on average processing speed
  - Keep the performance in mind by rendering UI updates on a separate thread
- Implement batch compression for multiple files or directories:
  - Group files by target compression algorithm
  - Process groups in parallel using worker threads
  - Balance thread count based on CPU cores
  - Make an exception for LZX compression, because it already uses multiple processor threads to compress files, as opposed to Xpress*K's single-threaded operation
- Improve system directory exclusion (with configurable rules)
- Implement Chromium cache directory detection to avoid compressing already compressed cache files, in order to:
  - Exclude `*\Cache\Cache_Data\` directory compression (of Chromium-based web browsers and Electron apps)
  - Exclude Telegram's `\tdata\user_data\cache` and `\tdata\user_data\media_cache` compression
  - Exclude Microsoft Teams' `\LocalCache\Microsoft\MSTeams\*` compression
  - Exclude other most popular web browsers' cache directories compression
  - Make these exclusions dynamic, not hard-coded - some entropy analysis might be required
- Implement checking the compression status of the poorly compressed files in parallel (to make use of other cores)
- Log this in the "info" channel to notify the user (me) about such files
- Add basic test suite for core functionality
  - Implement a single-thread benchmark to check if the CPU is fast enough to use LZX compress (to check if the CPU is not an Intel Atom with its numerous, but weak cores)ion (to check if the CPU is not an Intel Atom with its numerous, but weak cores)
  - Test compression detection accuracy
  - Verify that API calls work correctly
  - Check error handling paths

### Long-term Goals (v0.x.x)
- Create a 1-click/unattended mode of operation:
  - Automatically discover large folders (replacing WizTree and having to manually scour through folders)
  - Avoiding compressing specific folders, such as ones mentioned in short-term goals
  - Make life easier for The Greatest Technicians That Have Ever Lived
- Implement smart compression detection:
  - Use entropy analysis for compressibility estimation
  - Sample data chunks strategically
  - Cache results per file type
  - Add file type detection beyond extensions, i.e. based on file content
    - Compress easily compressable files (based on the extension first), then decide what to do with potentially problematic files later
- Quality of Life features:
  - More coloured output
  - Saving user configuration with an optional `.ini` file
  - Add resume capability for interrupted operations
  - Add option to generate detailed reports in various formats
- Localization support depending on system language
- Research advanced compression methods:
  - Evaluate alternative NTFS compression APIs, like [UPX](https://github.com/upx/upx)
  - Consider filesystem-agnostic approaches (moving compressed files in/out of the source drive unpacks them)
  - Benchmark different compression strategies
  - Research possibilities for custom compression algorithms
  - Investigate integration with other Windows compression features
- Security and Reliability:
  - Implement proper error handling for network paths
  - Add verification of filesystem compatibility