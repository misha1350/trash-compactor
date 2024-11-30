import bisect, logging, re, subprocess
from pathlib import Path
from .config import SKIP_EXTENSIONS, SIZE_THRESHOLDS, MIN_COMPRESSIBLE_SIZE

def get_size_category(file_size: int) -> str:
    """Determine size category of file using binary search"""
    sizes, categories = zip(*SIZE_THRESHOLDS)
    index = bisect.bisect_right(sizes, file_size)
    return categories[index] if index < len(categories) else 'large'

def should_compress_file(file_path: Path) -> bool:
    """Check if file is eligible for compression based on extension, size, and compression status"""
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return False

    if file_path.stat().st_size < MIN_COMPRESSIBLE_SIZE:
        return False
    
    try:
        cmd = f'compact "{str(file_path)}"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        
        # Look for compression status line
        status_pattern = r"(\d+) are compressed and (\d+) are not compressed"
        match = re.search(status_pattern, result.stdout)
        
        if match:
            compressed_count = int(match.group(1))
            return compressed_count == 0  # Return True if file is not compressed
            
        logging.warning(f"Could not determine compression status for {file_path}")
        return False
        
    except Exception as e:
        logging.error(f"Error checking compression status for {file_path}: {str(e)}")
        return False