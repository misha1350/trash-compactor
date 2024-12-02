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

# Algorithm selection based on file size
COMPRESSION_ALGORITHMS = {
    'tiny': 'XPRESS4K',
    'small': 'XPRESS8K',
    'medium': 'XPRESS16K',
    'large': 'XPRESS16K'  # Default to XPRESS16K for 'large' files
}