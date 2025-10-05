# Trash-Compactor
  A utility for intelligent file compression on Windows 10/11 systems using the built-in NTFS compression algorithms and Windows' built-in "compact.exe" utility. Unlike [CompactGUI](https://github.com/IridiumIO/CompactGUI) (another tool that is based on compact.exe and primarily designed for compressing Steam games), this utility automatically selects the optimal compression algorithm based on file size - this lets you squeeze the most out of the compression algorithms and get even smaller file sizes, all while avoiding unnecessary compression, keeping things DRY (also known as "Don't Repeat Yourself").

  ## Features

  - Automated compression using Windows NTFS compression
  - Smart algorithm selection based on file size
  - Multiple operation modes for different use cases
  - Skips poorly-compressed file formats (zip, media files, etc.)
  - Skips already-compressed files
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

### Operation Modes

Trash-Compactor offers three distinct operation modes to handle different scenarios:

#### Normal Mode (Default)
For first-time compression of directories with optimal performance.
Most users can just compress once and forget about it.
Be aware that temporarily disabling the anti-virus or whitelisting this program is going to greatly improve the compression speed.
```powershell
.\trash-compactor.exe C:\path\to\compress
```

#### Thorough Mode (-t)
For daily or scheduled compression tasks on directories that have already been compressed. Uses more intensive checking to accurately identify compressed files and avoid reprocessing (because Windows doesn't have reliable and fast methods to check if some files have been compressed before).
```powershell
.\trash-compactor.exe -t C:\path\to\compress
```

#### Branding Mode (-b)
For ensuring proper marking of files as compressed in Windows. Run this after initial compression if you plan to do daily or scheduled compression tasks, either after the Thorough Mode or after that.
```powershell
.\trash-compactor.exe -b C:\path\to\compress
```

#### Disabling (-x) or Forcing (-f) LZX Compression
LZX compression is turned **on** for large files by default.
LZX compression is resource-intensive and may impact performance a bit more, though it does result in better compression of both compressible binaries and the files that XPRESS16K doesn't compress well. But if you have a computer that was build or made before AD 2021, or if battery life is absolutely critical for you (a big problem on Intel Coffee Lake laptops), you may want to disable it the older your computer is.

### Recommended Workflow for Scheduled Compression

For optimal results when running compression tasks regularly (daily/weekly):

1. **Initial compression**: Run in normal mode
   ```powershell
   .\trash-compactor.exe C:\path\to\compress
   ```

2. **Branding**: Run in branding mode to properly mark all files
   ```powershell
   .\trash-compactor.exe -b C:\path\to\compress
   ```

3. **For ongoing daily/scheduled tasks**: Use thorough mode aftwewards
   ```powershell
   .\trash-compactor.exe -t C:\path\to\compress
   ```

### Additional Options

- `-v, --verbose`: Enable detailed output
- `-x, --no-lzx`: Disable LZX compression for better system responsiveness
- `-f, --force-lzx`: Force LZX compression even on less capable CPUs

## Development

To contribute to this project:

1. Fork the repository.
2. Create a new branch for your feature.
3. Submit a pull request.

## To-Do

### Short-term Goals (v0.4.0)
- Improve system directory exclusion (with configurable rules)
- Implement Chromium cache directory detection to avoid compressing already compressed cache files, in order to:
  - Exclude `*\Cache\Cache_Data\` directory compression (of Chromium-based web browsers and Electron apps)
  - Exclude Telegram's `\tdata\user_data\cache` and `\tdata\user_data\media_cache` compression
  - Exclude Microsoft Teams' `\LocalCache\Microsoft\MSTeams\*` compression
  - Exclude other most popular web browsers' cache directories compression
  - Make these exclusions dynamic, not hard-coded - some entropy analysis might be required
- Notify user if specific files have been compressed poorly
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
- Research advanced compression methods:
  - Evaluate alternative NTFS compression APIs, like [UPX](https://github.com/upx/upx)
  - Consider filesystem-agnostic approaches (moving compressed files in/out of the source drive unpacks them)
  - Benchmark different compression strategies
  - Research possibilities for custom compression algorithms
  - Investigate integration with other Windows compression features
- Quality of Life features:
  - Saving user configuration with an optional `.ini` file
  - Add resume capability for interrupted operations
- Localization support depending on system language
- Security and Reliability:
  - Implement proper error handling for network paths
  - Add verification of filesystem compatibility
