import bisect
import logging
import ctypes
from ctypes import wintypes
from pathlib import Path
from .config import SKIP_EXTENSIONS, SIZE_THRESHOLDS, MIN_COMPRESSIBLE_SIZE

def get_size_category(file_size: int) -> str:
    """Determine size category of file using binary search"""
    sizes, categories = zip(*SIZE_THRESHOLDS)
    index = bisect.bisect_right(sizes, file_size)
    return categories[index] if index < len(categories) else 'large'

#TODO: This works somewhat
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
    return compressed_size < actual_size, compressed_size

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