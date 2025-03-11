import logging, os, argparse, sys
from colorama import init, Fore, Style
from src import compress_directory, print_compression_summary, get_cpu_info, config, compress_directory_legacy

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
    root_logger.handlers = []
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
    version = "0.2.6"  # Updated version number
    build_date = "who cares"
    print(Fore.GREEN + f"Version: {version}    Build Date: {build_date}\n")
    
    parser = argparse.ArgumentParser(description="Compress files using Windows NTFS compression")
    parser.add_argument("directory", nargs="?", help="Directory to compress")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug output")
    parser.add_argument("-x", "--no-lzx", action="store_true", help="Disable LZX compression for better system responsiveness")
    parser.add_argument("-f", "--force-lzx", action="store_true", help="Force LZX compression even on less capable CPUs")
    
    # Create mutually exclusive group for operation modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("-b", "--brand-files", action="store_true", 
                      help="(Branding mode) Brand files as compressed using legacy method. Use after normal compression for proper marking.")
    mode_group.add_argument("-t", "--thorough", action="store_true",
                      help="(Thorough mode) Use slower but more accurate file checking. Use for daily/scheduled compression tasks.")
    
    args = parser.parse_args()

    # Determine if we should use LZX based on flags and CPU capability
    use_lzx = not args.no_lzx
    force_lzx = args.force_lzx
    
    setup_logging(args.verbose)
    
    if args.verbose:
        print(Fore.BLUE + "-v: Verbose output enabled" + Style.RESET_ALL)
    
    if not is_admin():
        logging.error("This script requires administrator privileges")
        return
    
    # Show pro tips only if no command-line flags or only a path is specified
    show_tips = not any([arg.startswith('-') for arg in sys.argv[1:] if arg != sys.argv[0]])
    
    # Tips are displayed if no command-line flags are set
    if show_tips:
        print(Fore.YELLOW + "\nPro tips:" + Style.RESET_ALL)
        print(Fore.CYAN + "• Run with -v to see what's happening under the hood 🔧")
        print(Fore.CYAN + "• Run with -x to disable LZX compression 🐌")
        print(Fore.CYAN + "• Run with -f to force LZX compression on less capable CPUs 🚀")
        print(Fore.CYAN + "• Run with -t for thorough checking when using scheduled compression ⏰")
        print(Fore.CYAN + "• Run with -b to brand files using legacy method (separate branding mode) 🏷️")
        print(Fore.CYAN + "• Use -h to display the help message (boring stuff) 📖")

    physical_cores, logical_cores = get_cpu_info()
    cpu_capable_for_lzx = config.is_cpu_capable_for_lzx()

    # Operation mode info messages
    if args.brand_files:
        print(Fore.YELLOW + "\nRunning in branding mode:" + Style.RESET_ALL)
        print(Fore.YELLOW + "This mode will help ensure files are properly marked as compressed in Windows." + Style.RESET_ALL)
        print(Fore.YELLOW + "Use this after normal compression to prevent re-processing of files in future runs." + Style.RESET_ALL)    
    elif args.thorough:
        print(Fore.YELLOW + "\nRunning in thorough checking mode:" + Style.RESET_ALL)
        print(Fore.YELLOW + "This mode performs more accurate but slower compression status checks." + Style.RESET_ALL)
        print(Fore.YELLOW + "Ideal for scheduled/daily compression tasks on previously compressed directories." + Style.RESET_ALL)
    
    # Decide whether to use LZX based on CPU capability and command line arguments
    if use_lzx:
        if cpu_capable_for_lzx or force_lzx:
            config.COMPRESSION_ALGORITHMS['large'] = 'LZX'
            if force_lzx and not cpu_capable_for_lzx:
                logging.info(f"Forcing LZX compression despite CPU having only {physical_cores} cores and {logical_cores} threads")
            else:
                logging.info(f"Using LZX compression (CPU deemed capable - it has {physical_cores} cores and {logical_cores} threads)")
        else:
            use_lzx = False
            print(Fore.YELLOW + f"\nNotice: Your CPU has {physical_cores} cores and {logical_cores} threads.")
            print(f"LZX compression requires at least {config.MIN_PHYSICAL_CORES_FOR_LZX} cores and {config.MIN_LOGICAL_CORES_FOR_LZX} threads.")
            print("LZX compression has been disabled for better system responsiveness.")
            print("Use -f flag to force LZX if you're feeling adventurous.")
    else:
        if args.no_lzx:
            print(Fore.YELLOW + "-x: LZX compression disabled via command line flag.")
        else:
            print(Fore.YELLOW + f"\nNotice: Your CPU has {physical_cores} cores and {logical_cores} threads.")
            print("LZX compression has been disabled for better system responsiveness.")

    directory = args.directory
    if not directory:
        directory = sanitize_path(input("Enter directory path to compress: "))
    else:
        directory = sanitize_path(directory)
    
    if not os.path.exists(directory):
        logging.error("Directory does not exist!")
        return

    # TODO: Add a check for Windows system directories among the subdirectories, instead of having a simple check for the root directory
    if os.path.normpath(directory).lower().startswith(r"c:\windows"):
        logging.error("To compress Windows system files, please use 'compact.exe /compactos:always' instead")
        return
    
    # Handle different operation modes
    if args.brand_files:
        print(Fore.CYAN + "\nStarting file branding process..." + Style.RESET_ALL)
        # Use thorough checking for branding only if explicitly requested
        legacy_stats = compress_directory_legacy(directory, thorough_check=args.thorough)
        
        # Print summary of legacy branding process
        print(Fore.CYAN + "\nFile Branding Summary:" + Style.RESET_ALL)
        print(f"Total files processed: {legacy_stats.total_files}")
        print(f"Files branded as compressed: {legacy_stats.branded_files}")
        if legacy_stats.branded_files > 0:
            print(f"Percentage of files branded: {(legacy_stats.branded_files / legacy_stats.total_files) * 100:.2f}%")
        if legacy_stats.still_unmarked > 0:
            print(Fore.YELLOW + f"Warning: {legacy_stats.still_unmarked} files are still not properly marked as compressed.")
            print("These files may be repeatedly processed in future runs.")
    else:
        # Normal or thorough compression mode
        logging.info(f"Starting compression of directory: {directory}")
        stats = compress_directory(directory, verbose=args.verbose, thorough_check=args.thorough)
        print_compression_summary(stats)
        
        if not args.thorough:
            print(Fore.YELLOW + "\nPro tips for scheduled compression tasks:" + Style.RESET_ALL)
            print("• Use the -t flag for thorough checking when running daily compression tasks")
            print("• After initial compression, run with the -b flag to properly brand all compressed files")
    
    print("\nOperation completed.")
    
    # Prompt to press any key to exit
    try:
        print(Fore.YELLOW + "\nPress any key to exit..." + Style.RESET_ALL)
        import msvcrt
        msvcrt.getch()
    except ImportError:
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()