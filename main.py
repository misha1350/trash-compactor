import argparse
import logging
import sys
from typing import Iterable

from colorama import Fore, Style, init

from src import (
    compress_directory,
    compress_directory_legacy,
    config,
    get_cpu_info,
    print_compression_summary,
    set_worker_cap,
)
from src.console import display_banner, prompt_exit
from src.launch import acquire_directory, interactive_configure
from src.runtime import confirm_hdd_usage, configure_lzx, is_admin, is_windows_system_path

VERSION = "0.3.2"
BUILD_DATE = "who cares"

PRO_TIPS: Iterable[str] = (
    "• Run with -v to see what's happening under the hood 🔧",
    "• Run with -x to disable LZX compression 🐌",
    "• Run with -f to force LZX compression on less capable CPUs 🚀",
    "• Run with -t for thorough checking when using scheduled compression ⏰",
    "• Run with -b to brand files using legacy method (separate branding mode) 🏷️",
    "• Run with -s if you intend to compress files on an HDD instead of an SSD 🛑",
    "• Use -h to display the help message (boring stuff) 📖",
)

SCHEDULE_TIPS: Iterable[str] = (
    "• Use the -t flag for thorough checking when running daily compression tasks",
    "• After initial compression, run with the -b flag to properly brand all compressed files",
)


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
    parser.add_argument(
        "-s",
        "--single-worker",
        action="store_true",
        help="Throttle compression to a single worker to reduce disk fragmentation risk",
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


def should_show_tips(args: argparse.Namespace) -> bool:
    return not (
        args.verbose
        or args.no_lzx
        or args.force_lzx
        or args.brand_files
        or args.thorough
        or getattr(args, "single_worker", False)
    )


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
    if getattr(args, "single_worker", False):
        print(Fore.YELLOW + "Single-worker mode enabled: compression batches will run sequentially." + Style.RESET_ALL)


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

    # if not thorough:
    #     print(Fore.YELLOW + "\nPro tips for scheduled compression tasks:" + Style.RESET_ALL)
    #     for tip in SCHEDULE_TIPS:
    #         print(tip)


def main() -> None:
    init(autoreset=True)
    display_banner(VERSION, BUILD_DATE)

    args = build_parser().parse_args()

    if args.no_lzx and args.force_lzx:
        print(Fore.RED + "Error: Cannot disable and force LZX compression at the same time." + Style.RESET_ALL)
        sys.exit(1)

    interactive_launch = len(sys.argv) == 1

    if interactive_launch:
        args = interactive_configure(args)

    setup_logging(args.verbose)

    if args.verbose:
        print(Fore.BLUE + "-v: Verbose output enabled" + Style.RESET_ALL)

    set_worker_cap(1 if args.single_worker else None)

    if not is_admin():
        logging.error("This script requires administrator privileges")
        prompt_exit()
        return

    # if not should_show_tips(args):
    #     display_tips(PRO_TIPS)

    physical_cores, logical_cores = get_cpu_info()
    announce_mode(args)

    configure_lzx(
        choice_enabled=not args.no_lzx,
        force_lzx=args.force_lzx,
        cpu_capable=config.is_cpu_capable_for_lzx(),
        physical=physical_cores,
        logical=logical_cores,
    )

    directory, args = acquire_directory(args, interactive_launch)
    args.directory = directory

    # TODO: extend this guard to check nested Windows system directories, not just the root
    if is_windows_system_path(directory):
        logging.error("To compress Windows system files, please use 'compact.exe /compactos:always' instead")
        prompt_exit()
        return

    if not confirm_hdd_usage(directory, force_serial=args.single_worker):
        prompt_exit()
        return

    if args.brand_files:
        run_branding(directory, thorough=args.thorough)
    else:
        run_compression(directory, verbose=args.verbose, thorough=args.thorough)

    print("\nOperation completed.")
    prompt_exit()


if __name__ == "__main__":
    main()
