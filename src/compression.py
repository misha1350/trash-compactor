import os
import subprocess
import logging
import ctypes
import sys
from pathlib import Path
from .config import COMPRESSION_ALGORITHMS, SKIP_EXTENSIONS, MIN_COMPRESSIBLE_SIZE
from .file_utils import get_size_category, should_compress_file, is_file_compressed
from .stats import CompressionStats, Spinner, LegacyCompressionStats

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

def legacy_compress_file(file_path: Path) -> bool:
    """Compress a file using the simple compact command for branding purposes"""
    try:
        # Normalize path
        file_path = Path(file_path).resolve()
         
        # Use raw string for Windows paths
        cmd = fr'compact /c "{str(file_path)}"'
         
        # Run command
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
         
        result = subprocess.run(
            cmd,
            capture_output=True, 
            text=True,
            startupinfo=startupinfo,
            shell=True
        )
         
        # Debug logging
        logging.debug(f"Command: {cmd}")
        logging.debug(f"Output: {result.stdout}")
        
        return result.returncode == 0
         
    except Exception as e:
        logging.error(f"Error branding {file_path}: {str(e)}")
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

def compress_directory(directory_path: str, verbose: bool = False) -> CompressionStats:
    """Main function to compress files in directory and subdirectories"""
    stats = CompressionStats()
    spinner = None
    base_dir = os.path.abspath(directory_path)
    
    if not verbose:
        spinner = Spinner()
        # Start with just the prefix, no file path yet
        spinner.start(message_prefix=" Compressing Files: ", message_suffix="")
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file
            
            try:
                should_compress, reason, current_size = should_compress_file(file_path)
                
                # Track original file size for all files
                file_size = file_path.stat().st_size
                stats.total_original_size += file_size
                
                if should_compress:
                    # Update spinner with current file (only in non-verbose mode)
                    if not verbose and spinner:
                        spinner.stop()
                        formatted_path = spinner.format_path(str(file_path), base_dir)
                        spinner.start(message_prefix=" Compressing Files: ", message_suffix=formatted_path)
                        
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
    
    # Stop the spinner before returning
    if not verbose and spinner:
        spinner.stop()

    return stats

def compress_directory_legacy(directory_path: str) -> LegacyCompressionStats:
    """Apply legacy compression method to help brand files as compressed"""
    stats = LegacyCompressionStats()
    base_dir = os.path.abspath(directory_path)
    
    print(f"\nChecking files in {directory_path} for proper compression branding...\n")
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            file_path = Path(root) / file
            
            try:
                stats.total_files += 1
                
                # Skip files with extensions that are known to be already compressed
                if file_path.suffix.lower() in SKIP_EXTENSIONS:
                    continue
                
                # Check if file is large enough to compress
                file_size = file_path.stat().st_size
                if file_size < MIN_COMPRESSIBLE_SIZE:
                    continue
                
                # Check if the file is already branded as compressed
                is_compressed, _ = is_file_compressed(file_path)
                
                # Only brand files that SHOULD be compressed but AREN'T currently branded
                if not is_compressed:
                    relative_path = os.path.relpath(str(file_path), base_dir)
                    print(f"Branding file: {relative_path}")
                    
                    if legacy_compress_file(file_path):
                        stats.branded_files += 1
                        
                        # DEBUG: Verify if the file is now recognized as compressed
                        is_compressed, _ = is_file_compressed(file_path)
                        if not is_compressed:
                            stats.still_unmarked += 1
                            print(f"WARNING: File still not recognized as compressed: {relative_path}")
                
            except Exception as e:
                error_msg = f"Error processing {file_path}: {str(e)}"
                stats.errors.append(error_msg)
                print(f"ERROR: {error_msg}")
    
    return stats