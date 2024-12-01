import logging, os, argparse, sys
from datetime import datetime
from colorama import init, Fore, Style
from src import compress_directory, print_compression_summary

def is_admin():
    """Check if script has admin privileges"""
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    
def sanitize_path(path):
    """Clean up and validate input path"""
    path = path.strip("' \"")
    normalized_path = os.path.normpath(path)
    return normalized_path

def setup_logging(verbose: bool):
    """Configure logging based on verbosity"""
    class CustomFormatter(logging.Formatter):
        def format(self, record):
            # Strip 'root' from the output
            if record.levelno == logging.DEBUG and verbose:
                return f"DEBUG: {record.getMessage()}"
            elif record.levelno == logging.INFO:
                return f"{record.getMessage()}"
            elif record.levelno >= logging.WARNING:
                return f"{record.levelname}: {record.getMessage()}"
            return ""

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    
    root_logger = logging.getLogger()
    root_logger.handlers = []  # Remove existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

def main():
    init(autoreset=True)  # Initialize colorama

    # Splash screen with colored ASCII art
    print(Fore.CYAN + Style.BRIGHT + r"""
 _____               _             ___                                 _             
/__   \_ __ __ _ ___| |__         / __\___  _ __ ___  _ __   __ _  ___| |_ ___  _ __ 
  / /\/ '__/ _` / __| '_ \ _____ / /  / _ \| '_ ` _ \| '_ \ / _` |/ __| __/ _ \| '__|
 / /  | | | (_| \__ \ | | |_____/ /__| (_) | | | | | | |_) | (_| | (__| || (_) | |   
 \/   |_|  \__,_|___/_| |_|     \____/\___/|_| |_| |_| .__/ \__,_|\___|\__\___/|_|   
                                                     |_|                             """)
    version = "0.2.0"  # Update manually or via build process
    build_date = "who cares"
    print(Fore.GREEN + f"Version: {version}    Build Date: {build_date}\n")
    parser = argparse.ArgumentParser(description="Compress files using Windows NTFS compression")
    parser.add_argument("directory", nargs="?", help="Directory to compress")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    if not is_admin():
        logging.error("This script requires administrator privileges")
        return
    
    if not args.verbose and not any(arg.startswith('-') for arg in sys.argv[1:]):
        print(Fore.YELLOW + "\nPro tips:" + Style.RESET_ALL)
        print(Fore.CYAN + "• Run with -v to see what's happening under the hood 🔧")
        print(Fore.CYAN + "• Use -h to display the help message (boring stuff) 📖")
    
    directory = args.directory
    if not directory:
        directory = sanitize_path(input("Enter directory path to compress: "))
    else:
        directory = sanitize_path(directory)
    
    if not os.path.exists(directory):
        logging.error("Directory does not exist!")
        return
    
    if os.path.normpath(directory).lower().startswith(r"c:\windows"):
        logging.error("To compress Windows system files, please use 'compact.exe /compactos:always' instead")
        return
    
    logging.info(f"Starting compression of directory: {directory}")
    stats = compress_directory(directory)
    print_compression_summary(stats)
    print("\nCompression completed.")

if __name__ == "__main__":
    main()