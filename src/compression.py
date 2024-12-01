import os
import subprocess
import logging
import ctypes
from pathlib import Path
from .config import COMPRESSION_ALGORITHMS
from .file_utils import get_size_category, should_compress_file, is_file_compressed
from .stats import CompressionStats

def compress_file(file_path: Path, algorithm: str) -> bool:
    """Compress single file using compact command"""
    try:
        file_path = file_path.resolve()
        cmd = fr'compact /c /a /exe:{algorithm} "{str(file_path)}"'

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            shell=True
        )

        return result.returncode == 0

    except Exception as e:
        logging.error(f"Error compressing {file_path}: {str(e)}")
        return False

def get_compressed_size(file_path: Path) -> int:
    GetCompressedFileSizeW = ctypes.windll.kernel32.GetCompressedFileSizeW
    GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    GetCompressedFileSizeW.restype = ctypes.c_ulong

    compressed_high = ctypes.c_ulong(0)
    compressed_low = GetCompressedFileSizeW(str(file_path), ctypes.byref(compressed_high))
    if compressed_low == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error != 0:
            raise ctypes.WinError(error)

    compressed_size = (compressed_high.value << 32) + compressed_low
    return compressed_size

def compress_directory(directory_path: str) -> CompressionStats:
    """Main function to compress files in directory and subdirectories"""
    stats = CompressionStats()
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file
            
            try:
                should_compress, reason, current_size = should_compress_file(file_path)
                
                # Track original file size for all files
                file_size = file_path.stat().st_size
                stats.total_original_size += file_size
                
                if should_compress:
                    # Compress file
                    if compress_file(file_path, algorithm := COMPRESSION_ALGORITHMS[get_size_category(file_size)]):
                        _, compressed_size = is_file_compressed(file_path)
                        stats.compressed_files += 1
                        stats.total_compressed_size += compressed_size
                        logging.debug(f"Compressed {file_path} using {algorithm}")
                    else:
                        stats.skipped_files += 1
                        stats.total_compressed_size += file_size
                        logging.debug(f"Compression failed for {file_path}")
                else:
                    stats.skipped_files += 1
                    stats.total_compressed_size += current_size
                    if "already compressed" in reason.lower():
                        stats.already_compressed_files += 1
                    logging.debug(f"Skipping {file_path}: {reason}")

            except Exception as e:
                stats.errors.append(f"Error processing {file_path}: {str(e)}")
                stats.skipped_files += 1
                try:
                    stats.total_compressed_size += file_path.stat().st_size
                except:
                    pass
                logging.error(f"Error processing {file_path}: {str(e)}")

    return stats