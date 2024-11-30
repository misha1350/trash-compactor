import os
import subprocess
import logging
import ctypes
from ctypes import wintypes
from pathlib import Path
from .config import COMPRESSION_ALGORITHMS
from .file_utils import get_size_category, should_compress_file
from .stats import CompressionStats

def compress_file(file_path: Path, algorithm: str) -> bool:
    """Compress single file using compact command"""
    try:
        # Normalize path
        file_path = Path(file_path).resolve()
        
        # Use raw string for Windows paths
        cmd = fr'compact /c /a /exe:{algorithm} "{str(file_path)}"'
        
        # Run as admin and capture output
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            cmd,
            capture_output=True, 
            text=True,
            startupinfo=startupinfo,
            shell=True  # Required for Windows paths with spaces
        )
        
        # Debug logging
        logging.debug(f"Command: {cmd}")
        logging.debug(f"Output: {result.stdout}")
        logging.debug(f"Error: {result.stderr}")
        
        return result.returncode == 0
        
    except Exception as e:
        logging.error(f"Error compressing {file_path}: {str(e)}")
        return False
    
def get_compressed_size(file_path: Path) -> int:
    GetCompressedFileSizeW = ctypes.windll.kernel32.GetCompressedFileSizeW
    GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, wintypes.LPDWORD]
    GetCompressedFileSizeW.restype = wintypes.DWORD

    file_size_high = wintypes.DWORD(0)
    file_size_low = GetCompressedFileSizeW(str(file_path), ctypes.byref(file_size_high))

    if file_size_low == 0xFFFFFFFF:
        last_error = ctypes.GetLastError()
        if last_error != 0:
            raise ctypes.WinError(last_error)

    compressed_size = (file_size_high.value << 32) + file_size_low
    return compressed_size

def compress_directory(directory_path: str) -> CompressionStats:
    """Main function to compress files in directory and subdirectories"""
    stats = CompressionStats()
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file
            
            try:
                # Skip if file shouldn't be compressed
                if not should_compress_file(file_path):
                    print(f"Decided not to compress {file_path}")
                    stats.skipped_files += 1
                    continue

                # Get file size and determine algorithm
                file_size = file_path.stat().st_size
                size_category = get_size_category(file_size)
                algorithm = COMPRESSION_ALGORITHMS[size_category]

                # Compress file
                if compress_file(file_path, algorithm):
                    original_size = file_size  # Store original size before compression
                    compressed_size = get_compressed_size(file_path)  # Get compressed size
                    
                    stats.compressed_files += 1
                    stats.total_original_size += original_size
                    stats.total_compressed_size += compressed_size
                else:
                    print(f"Skipped {file_path}")
                    stats.skipped_files += 1

            except Exception as e:
                stats.errors.append(f"Error processing {file_path}: {str(e)}")
                stats.skipped_files += 1

    return stats