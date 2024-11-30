from typing import Set, Tuple

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

# Algorithm selection based on file size
COMPRESSION_ALGORITHMS = {
    'tiny': 'XPRESS4K',
    'small': 'XPRESS8K',
    'medium': 'XPRESS16K',
    'large': 'LZX'
}
