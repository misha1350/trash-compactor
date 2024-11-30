# Trash-Compactor
A utility for intelligent file compression on Windows 10/11 systems using the built-in NTFS compression algorithms and the "compact.exe" utility. Unlike CompactGUI, this utility automatically selects the optimal compression algorithm based on file size - this lets you squeeze the most out of the compression algorithms and get even smaller file sizes.

## Features

- Automated compression using Windows NTFS compression
- Smart algorithm selection based on file size
- Skips poorly-compressed file formats (zip, media files, etc.)
- Skips already-compressed files (which compact.exe has already compressed)
- Detailed compression statistics
- Requires administrator privileges

## Requirements

- Windows 10/11
- Python 3.8+
- Administrator privileges

## Installation

1. Open PowerShell as Administrator:
    - Right-click Start Menu
    - Select "Windows PowerShell (Admin)" or "Windows Terminal (Admin)"

2. Clone and navigate to the repository:
    ```powershell
    git clone https://github.com/misha1350/trash-compactor.git
    cd trash-compactor
    ```

3. Run the program:
    ```powershell
    python main.py
    ```

Note: Make sure Git and Python 3.8+ are installed on your system.

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