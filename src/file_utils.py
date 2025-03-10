import bisect
import logging
import ctypes
import subprocess
import re
from ctypes import wintypes
from pathlib import Path
from .config import SKIP_EXTENSIONS, SIZE_THRESHOLDS, MIN_COMPRESSIBLE_SIZE

def get_size_category(file_size: int) -> str:
    """Determine size category of file using binary search"""
    sizes, categories = zip(*SIZE_THRESHOLDS)
    index = bisect.bisect_right(sizes, file_size)
    return categories[index] if index < len(categories) else 'large'

"""
Rant time:
I've tried everything to get this function to work all the time, but:
some files simply cannot be checked for compression status.
Not with the GetCompressedFileSizeW function, not with the "compact /a" command.
I've spent an entire evening and millions of tokens on this, but it appears that the only way
would be to simply call "compact /c" on everything, if you intend to run this on a crontab every single day
and reliably skipping compressed files all the time.
Instead of designing a file system that can contain metadata for each file, like file permissions in Linux,
Microsoft decided to make reinvent the wheel, and new ways to force you to buy a larger SSD.
"""

def check_compression_with_compact(file_path: Path) -> bool:
    """Check if a file is compressed using compact command"""
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = f'compact /a "{str(file_path)}"'
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            shell=True,
            text=True
        )
        
        # If command execution failed, fall back to size comparison
        if result.returncode != 0:
            return False
        
        # Check for a specific substring in the output to determine compression status
        return "0 are not" in result.stdout
        
    except Exception as e:
        logging.error(f"Failed to check compression with compact: {e}")
        return False

def is_file_compressed(file_path: Path) -> tuple[bool, int]:
    """Check if a file is compressed and return its compressed size"""
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    
    # Get actual file size
    try:
        actual_size = file_path.stat().st_size
    except Exception as e:
        logging.error(f"Failed to get actual file size: {e}")
        return False, 0

    # Get compressed size
    GetCompressedFileSizeW = kernel32.GetCompressedFileSizeW
    GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    GetCompressedFileSizeW.restype = wintypes.DWORD

    high_order = wintypes.DWORD()
    low_order = GetCompressedFileSizeW(str(file_path), ctypes.byref(high_order))
    
    if low_order == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error != 0:
            logging.error(f"Failed to get compressed size: {ctypes.WinError(error)}")
            return False, actual_size
    
    compressed_size = (high_order.value << 32) + low_order
    
    # Primary check: compressed size less than actual size
    is_compressed_by_size = compressed_size < actual_size
    
    # If file is already deemed compressed by size check, no need for fallback
    if is_compressed_by_size:
        return True, compressed_size
        
    # Secondary check: Use compact command as a fallback when sizes are equal
    # but file might still be compressed without size reduction
    if compressed_size == actual_size:
        is_compressed_by_attr = check_compression_with_compact(file_path)
        if is_compressed_by_attr:
            logging.debug(f"File {file_path} detected as compressed by compact command")
            return True, compressed_size
            
    return False, compressed_size

def should_compress_file(file_path: Path) -> tuple[bool, str, int]:
    """Check if file is eligible for compression and return its compressed size"""
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return False, f"Skipped due to extension {file_path.suffix}", 0

    try:
        file_size = file_path.stat().st_size
        if file_size < MIN_COMPRESSIBLE_SIZE:
            return False, f"File too small ({file_size} bytes)", file_size

        is_compressed, compressed_size = is_file_compressed(file_path)
        if is_compressed:
            return False, "File is already compressed", compressed_size

        return True, "File eligible for compression", file_size

    except Exception as e:
        logging.error(f"Error checking file {file_path}: {str(e)}")
        return False, f"Error during check: {str(e)}", 0