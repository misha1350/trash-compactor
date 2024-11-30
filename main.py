import logging, os
from src import compress_directory, print_compression_summary

def is_admin():
    """Check if script has admin privileges"""
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

def main():
    if not is_admin():
        logging.error("This script requires administrator privileges")
        return
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    directory = input("Enter directory path to compress: ").strip()
    if not os.path.exists(directory):
        logging.error("Directory does not exist!")
        return
    
    if os.path.normpath(directory).lower().startswith(r"c:\windows"):
        logging.error("To compress Windows system files, please use 'compact.exe /compactos:always' instead")
        return
    
    logging.info(f"Starting compression of directory: {directory}")
    stats = compress_directory(directory)
    print_compression_summary(stats)

if __name__ == "__main__":
    main()