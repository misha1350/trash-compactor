import logging
import os
from typing import Optional

from colorama import Fore, Style

from . import config
from .console import EscapeExit, announce_cancelled, read_user_input
from .file_utils import is_hard_drive


def sanitize_path(path: str) -> str:
    return os.path.normpath(path.strip(" '\""))


def is_admin() -> bool:
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())


def is_windows_system_path(directory: str) -> bool:
    return os.path.normpath(directory).lower().startswith(r"c:\windows")


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
    pending = argument
    while True:
        try:
            source = pending if pending is not None else read_user_input("Enter directory path to compress: ")
        except (KeyboardInterrupt, EscapeExit):
            announce_cancelled()
            raise SystemExit(0)
        path = sanitize_path(source)
        if path:
            return path
        print(Fore.RED + "Directory path cannot be empty." + Style.RESET_ALL)
        pending = None


def confirm_hdd_usage(directory: str) -> bool:
    if not is_hard_drive(directory):
        return True

    print(Fore.YELLOW + "You may be attempting to compress files on a traditional spinning hard drive. (But the crude logic may be not working properly)")
    print("If it truly is the case, this can lead to file fragmentation and decreased performance. (solid state storage doesn't have this)" + Style.RESET_ALL)
    print(Fore.YELLOW + "\nRecommendation:" + Style.RESET_ALL)
    print("• Consider upgrading to an SSD for your system drive")
    print("• If you must use an HDD, be aware that compression may reduce overall performance")
    print("• Defragment your drive after compression completes")

    print("\n" + Fore.YELLOW + "Do you want to proceed anyway? (y/n): " + Style.RESET_ALL, end="")
    try:
        response = read_user_input("").strip().lower()
    except (KeyboardInterrupt, EscapeExit):
        announce_cancelled()
        return False
    if response not in {"y", "yes"}:
        print(Fore.CYAN + "Operation cancelled." + Style.RESET_ALL)
        return False

    print(Fore.YELLOW + "\nProceeding with compression on HDD. This may impact system performance." + Style.RESET_ALL)
    return True
