from typing import Set, Tuple
import psutil

SKIP_EXTENSIONS: Set[str] = {
    # Archives and compressed files (assuming they don't use "store" mode)
    '.zip', '.rar', '.7z', '.gz', '.xz', '.bz2', '.tar',
    '.iso', '.img', '.squashfs', '.appimage',
    
    # Images and graphics
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    '.heic', '.heif', '.avif', '.jxl', '.tiff',
    
    # Video formats
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v',
    '.hevc', '.h264', '.h265', '.vp8', '.vp9',
    '.av1', '.wmv', '.flv', '.3gp',
    
    # Audio formats
    '.mp3', '.aac', '.ogg', '.m4a', '.opus',
    '.flac', '.wav', '.wma', '.ac3', '.dts',
    '.alac', '.ape', '.aiff', '.pcm',
    '.vgz', '.vgm',
    
    # Virtual machine disk images
    '.vdi', '.vmdk', '.vhd', '.vhdx', '.qcow2',
    '.qed', '.vpc', '.hdd', '.raw',
    
    # Machine learning models
    '.gguf', '.h5', '.onnx', '.pb', '.tflite',
    '.safetensors', '.torch', '.pt',
    
    # Modern Office formats (already ZIP-based)
    '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.pdf'
}

MIN_COMPRESSIBLE_SIZE = 8 * 1024  # 8KB minimum
# Compression algorithm thresholds (in bytes)
SIZE_THRESHOLDS = [
    (8 * 1024, 'tiny'),        # 8KB
    (64 * 1024, 'small'),      # 64KB
    (256 * 1024, 'medium'),    # 256KB
    (1024 * 1024, 'large')     # 1MB
]

# Minimum requirements for LZX compression
MIN_LOGICAL_CORES_FOR_LZX = 5  # At least 5 logical cores (threads)
MIN_PHYSICAL_CORES_FOR_LZX = 3  # At least 3 physical cores

def get_cpu_info():
    """Get CPU physical cores and logical processors (threads)"""
    physical_cores = psutil.cpu_count(logical=False)
    logical_cores = psutil.cpu_count(logical=True)
    return physical_cores, logical_cores

def is_cpu_capable_for_lzx():
    """Check if CPU is powerful enough for LZX compression"""
    physical_cores, logical_cores = get_cpu_info()
    
    # CPU should have at least MIN_LOGICAL_CORES_FOR_LZX logical cores and
    # MIN_PHYSICAL_CORES_FOR_LZX physical cores to efficiently run LZX compression
    return (physical_cores >= MIN_PHYSICAL_CORES_FOR_LZX and 
            logical_cores >= MIN_LOGICAL_CORES_FOR_LZX)

# Algorithm selection based on file size
COMPRESSION_ALGORITHMS = {
    'tiny': 'XPRESS4K',
    'small': 'XPRESS8K',
    'medium': 'XPRESS16K',
    'large': 'XPRESS16K'  # Default to XPRESS16K for 'large' files
}