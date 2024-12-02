from typing import Set, Tuple
import psutil

SKIP_EXTENSIONS: Set[str] = {
    '.zip', '.rar', '.7z', '.gz', '.xz', '.bz2',
    '.jpg', '.jpeg', '.png', '.gif', '.webp',
    '.mp4', '.mkv', '.avi', '.mov',
    '.mp3', '.aac', '.ogg', '.m4a',
    '.opus', '.flac', '.wav', '.wma'
}

MIN_COMPRESSIBLE_SIZE = 4 * 1024  # 4KB minimum
# Compression algorithm thresholds (in bytes)
SIZE_THRESHOLDS = [
    (4 * 1024, 'tiny'),        # 4KB
    (64 * 1024, 'small'),      # 64KB
    (256 * 1024, 'medium'),    # 256KB
    (1024 * 1024, 'large')     # 1MB
]

def get_cpu_info():
    """Get CPU physical cores and logical processors (threads)"""
    physical_cores = psutil.cpu_count(logical=False)
    logical_cores = psutil.cpu_count(logical=True)
    return physical_cores, logical_cores

def should_use_lzx():
    """Determine if LZX compression should be used based on CPU capabilities"""
    physical_cores, logical_cores = get_cpu_info()
    
    # Strong CPU: 4+ physical cores with hyperthreading
    if physical_cores >= 4 and logical_cores > physical_cores:
        return True
    # Decent CPU: 4 cores without hyperthreading
    elif physical_cores >= 4:
        return True
    # Weak CPU: 2 cores (with or without hyperthreading)
    return False

# Algorithm selection based on file size
if should_use_lzx():
    COMPRESSION_ALGORITHMS = {
        'tiny': 'XPRESS4K',
        'small': 'XPRESS8K',
        'medium': 'XPRESS16K',
        'large': 'LZX'
    }
else:
    COMPRESSION_ALGORITHMS = {
        'tiny': 'XPRESS4K',
        'small': 'XPRESS8K',
        'medium': 'XPRESS16K',
        'large': 'XPRESS16K'  # Use XPRESS16K instead of LZX for weaker CPUs
    }