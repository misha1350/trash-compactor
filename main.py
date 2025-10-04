import argparse
import logging
import os
import sys
from typing import Iterable, Optional

from colorama import Fore, Style, init

from src import (
    compress_directory,
    compress_directory_legacy,
    config,
    get_cpu_info,
    print_compression_summary,
)
from src.file_utils import is_hard_drive

BANNER = r"""
 _____               _             ___                                 _             
/__   \_ __ __ _ ___| |__         / __\___  _ __ ___  _ __   __ _  ___| |_ ___  _ __ 
  / /\/ '__/ _` / __| '_ \ _____ / /  / _ \| '_ ` _ \| '_ \ / _` |/ __| __/ _ \| '__|
 / /  | | | (_| \__ \ | | |_____/ /__| (_) | | | | | | |_) | (_| | (__| || (_) | |   
 \/   |_|  \__,_|___/_| |_|     \____/\___/|_| |_| |_| .__/ \__,_|\___|\__\___/|_|   
                                                     |_|                             
"""

VERSION = "0.3.0"
BUILD_DATE = "who cares"

PRO_TIPS: Iterable[str] = (
    "• Run with -v to see what's happening under the hood 🔧",
    "• Run with -x to disable LZX compression 🐌",
    "• Run with -f to force LZX compression on less capable CPUs 🚀",
    "• Run with -t for thorough checking when using scheduled compression ⏰",
    "• Run with -b to brand files using legacy method (separate branding mode) 🏷️",
    "• Use -h to display the help message (boring stuff) 📖",
)

SCHEDULE_TIPS: Iterable[str] = (
    "• Use the -t flag for thorough checking when running daily compression tasks",
    "• After initial compression, run with the -b flag to properly brand all compressed files",
)


def is_admin() -> bool:
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())


def sanitize_path(path: str) -> str:
    return os.path.normpath(path.strip(" '\""))


def setup_logging(verbose: bool) -> None:
    class _Formatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            if record.levelno == logging.DEBUG and verbose:
                return f"DEBUG: {record.getMessage()}"
            if record.levelno == logging.INFO:
                return record.getMessage()
            if record.levelno >= logging.WARNING:
                return f"{record.levelname}: {record.getMessage()}"
            return ""

    handler = logging.StreamHandler()
    handler.setFormatter(_Formatter())

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compress files using Windows NTFS compression",
    )
    parser.add_argument("directory", nargs="?", help="Directory to compress")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug output")
    parser.add_argument(
        "-x",
        "--no-lzx",
        action="store_true",
        help="Disable LZX compression for better system responsiveness",
    )
    parser.add_argument(
        "-f",
        "--force-lzx",
        action="store_true",
        help="Force LZX compression even on less capable CPUs",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "-b",
        "--brand-files",
        action="store_true",
        help="(Branding mode) Brand files as compressed using legacy method. Use after normal compression for proper marking.",
    )
    mode_group.add_argument(
        "-t",
        "--thorough",
        action="store_true",
        help="(Thorough mode) Use slower but more accurate file checking. Use for daily/scheduled compression tasks.",
    )
    return parser


def display_banner() -> None:
    print(Fore.CYAN + Style.BRIGHT + BANNER)
    print(Fore.GREEN + f"Version: {VERSION}    Build Date: {BUILD_DATE}\n")


def should_show_tips() -> bool:
    return not any(arg.startswith('-') for arg in sys.argv[1:])


def display_tips(lines: Iterable[str]) -> None:
    print(Fore.YELLOW + "\nPro tips:" + Style.RESET_ALL)
    for line in lines:
        print(Fore.CYAN + line)


def announce_mode(args: argparse.Namespace) -> None:
    if args.brand_files:
        print(Fore.YELLOW + "\nRunning in branding mode:" + Style.RESET_ALL)
        print(Fore.YELLOW + "This mode will help ensure files are properly marked as compressed in Windows." + Style.RESET_ALL)
        print(Fore.YELLOW + "Use this after normal compression to prevent re-processing of files in future runs." + Style.RESET_ALL)
    elif args.thorough:
        print(Fore.YELLOW + "\nRunning in thorough checking mode:" + Style.RESET_ALL)
        print(Fore.YELLOW + "This mode performs more accurate but slower compression status checks." + Style.RESET_ALL)
        print(Fore.YELLOW + "Ideal for scheduled/daily compression tasks on previously compressed directories." + Style.RESET_ALL)


def configure_lzx(choice_enabled: bool, force_lzx: bool, cpu_capable: bool, physical: int, logical: int) -> bool:
    if not choice_enabled:
        if force_lzx:
            logging.info("Ignoring -f because -x disables LZX explicitly")
        print(Fore.YELLOW + "-x: LZX compression disabled via command line flag.")
        config.COMPRESSION_ALGORITHMS['large'] = 'XPRESS16K'
        return False

    if cpu_capable or force_lzx:
        config.COMPRESSION_ALGORITHMS['large'] = 'LZX'
        if force_lzx and not cpu_capable:
            logging.info(
                "Forcing LZX compression despite CPU having only %s cores and %s threads",
                physical,
                logical,
            )
        else:
            logging.info(
                "Using LZX compression (CPU deemed capable - it has %s cores and %s threads)",
                physical,
                logical,
            )
        return True

    config.COMPRESSION_ALGORITHMS['large'] = 'XPRESS16K'
    print(Fore.YELLOW + f"\nNotice: Your CPU has {physical} cores and {logical} threads.")
    print(f"LZX compression requires at least {config.MIN_PHYSICAL_CORES_FOR_LZX} cores and {config.MIN_LOGICAL_CORES_FOR_LZX} threads.")
    print("LZX compression has been disabled for better system responsiveness.")
    print("Use -f flag to force LZX if you're feeling adventurous.")
    return False


def resolve_directory(argument: Optional[str]) -> str:
    path = sanitize_path(argument or input("Enter directory path to compress: "))
    return path


def is_windows_system_path(directory: str) -> bool:
    return os.path.normpath(directory).lower().startswith(r"c:\windows")


def confirm_hdd_usage(directory: str) -> bool:
    if not is_hard_drive(directory):
        return True

    # print(Fore.RED + "\n⚠️ WARNING: HARD DISK DRIVE DETECTED! ⚠️" + Style.RESET_ALL)
    # print(Fore.RED + "You are attempting to compress files on a traditional spinning hard drive.")
    print(Fore.YELLOW + "You may be attempting to compress files on a traditional spinning hard drive. (But the crude logic may be not working properly)")
    print("If it truly is the case, this can lead to file fragmentation and decreased performance. (solid state storage doesn't have this)" + Style.RESET_ALL)
    print(Fore.YELLOW + "\nRecommendation:" + Style.RESET_ALL)
    print("• Consider upgrading to an SSD for your system drive")
    print("• If you must use an HDD, be aware that compression may reduce overall performance")
    print("• Defragment your drive after compression completes")

    print("\n" + Fore.YELLOW + "Do you want to proceed anyway? (y/n): " + Style.RESET_ALL, end="")
    response = input().strip().lower()
    if response not in {"y", "yes"}:
        print(Fore.CYAN + "Operation cancelled." + Style.RESET_ALL)
        return False

    print(Fore.YELLOW + "\nProceeding with compression on HDD. This may impact system performance." + Style.RESET_ALL)
    return True


def run_branding(directory: str, thorough: bool) -> None:
    print(Fore.CYAN + "\nStarting file branding process..." + Style.RESET_ALL)
    legacy_stats = compress_directory_legacy(directory, thorough_check=thorough)

    print(Fore.CYAN + "\nFile Branding Summary:" + Style.RESET_ALL)
    print(f"Total files processed: {legacy_stats.total_files}")
    print(f"Files branded as compressed: {legacy_stats.branded_files}")
    if legacy_stats.branded_files:
        percentage = (legacy_stats.branded_files / legacy_stats.total_files) * 100 if legacy_stats.total_files else 0
        print(f"Percentage of files branded: {percentage:.2f}%")
    if legacy_stats.still_unmarked:
        print(Fore.YELLOW + f"Warning: {legacy_stats.still_unmarked} files are still not properly marked as compressed.")
        print("These files may be repeatedly processed in future runs.")


def run_compression(directory: str, verbose: bool, thorough: bool) -> None:
    logging.info("Starting compression of directory: %s", directory)
    stats, monitor = compress_directory(directory, verbose=verbose, thorough_check=thorough)
    print_compression_summary(stats)
    monitor.print_summary()

    if not thorough:
        print(Fore.YELLOW + "\nPro tips for scheduled compression tasks:" + Style.RESET_ALL)
        for tip in SCHEDULE_TIPS:
            print(tip)


def prompt_exit() -> None:
    try:
        print(Fore.YELLOW + "\nPress any key to exit..." + Style.RESET_ALL)
        import msvcrt

        msvcrt.getch()
    except ImportError:
        input("\nPress Enter to exit...")


def main() -> None:
    init(autoreset=True)
    display_banner()

    args = build_parser().parse_args()
    setup_logging(args.verbose)

    if args.verbose:
        print(Fore.BLUE + "-v: Verbose output enabled" + Style.RESET_ALL)

    if not is_admin():
        logging.error("This script requires administrator privileges")
        return

    if should_show_tips():
        display_tips(PRO_TIPS)

    physical_cores, logical_cores = get_cpu_info()
    announce_mode(args)

    configure_lzx(
        choice_enabled=not args.no_lzx,
        force_lzx=args.force_lzx,
        cpu_capable=config.is_cpu_capable_for_lzx(),
        physical=physical_cores,
        logical=logical_cores,
    )

    directory = resolve_directory(args.directory)
    if not os.path.exists(directory):
        logging.error("Directory does not exist!")
        return

    # TODO: extend this guard to check nested Windows system directories, not just the root.
    if is_windows_system_path(directory):
        logging.error("To compress Windows system files, please use 'compact.exe /compactos:always' instead")
        return

    if not confirm_hdd_usage(directory):
        return

    if args.brand_files:
        run_branding(directory, thorough=args.thorough)
    else:
        run_compression(directory, verbose=args.verbose, thorough=args.thorough)

    print("\nOperation completed.")
    prompt_exit()


if __name__ == "__main__":
    main()