import os
import shlex
from argparse import Namespace
from dataclasses import dataclass

from colorama import Fore, Style

from .console import EscapeExit, announce_cancelled, read_user_input
from .runtime import resolve_directory, sanitize_path

FLAG_METADATA: dict[str, tuple[str, str]] = {
    'verbose': ('-v', 'Verbose output'),
    'no_lzx': ('-x', 'Disable LZX compression'),
    'force_lzx': ('-f', 'Force LZX compression'),
    'thorough': ('-t', 'Thorough checking mode'),
    'brand_files': ('-b', 'Branding mode'),
    'single_worker': ('-s', 'Throttle for HDDs'),
}


@dataclass
class LaunchState:
    directory: str = ""
    verbose: bool = False
    no_lzx: bool = False
    force_lzx: bool = False
    thorough: bool = False
    brand_files: bool = False
    single_worker: bool = False

    def toggle(self, key: str) -> None:
        # Mutually exclusive switches get untangled here so the prompt never lies
        enabled = not getattr(self, key)
        if key == 'thorough' and enabled:
            self.brand_files = False
        if key == 'brand_files' and enabled:
            self.thorough = False
        if key == 'no_lzx' and enabled:
            self.force_lzx = False
        if key == 'force_lzx' and enabled:
            self.no_lzx = False
        setattr(self, key, enabled)


def _format_active_flags(state: LaunchState) -> str:
    items: list[str] = []
    for key, (flag, description) in FLAG_METADATA.items():
        if getattr(state, key):
            items.append(f"{description} ({flag})")
    return ", ".join(items) if items else "<none>"


def _print_flag_reference() -> None:
    print(Fore.YELLOW + "\nAvailable flags:" + Style.RESET_ALL)
    for key, (flag, description) in FLAG_METADATA.items():
        print(f"  {flag:<6} {description}")


def _apply_flag_string(raw: str, state: LaunchState) -> None:
    tokens = shlex.split(raw, posix=False)
    if not tokens:
        return

    short_map = {'v': 'verbose', 'x': 'no_lzx', 'f': 'force_lzx', 't': 'thorough', 'b': 'brand_files'}
    long_map = {
        'verbose': 'verbose',
        'no-lzx': 'no_lzx',
        'force-lzx': 'force_lzx',
        'thorough': 'thorough',
        'brand-files': 'brand_files',
        'single-worker': 'single_worker',
    }
    short_map['s'] = 'single_worker'

    for token in tokens:
        if token.startswith('--'):
            flag_key = long_map.get(token[2:])
            if flag_key:
                state.toggle(flag_key)
            continue

        if token.startswith('-') and len(token) > 1:
            for char in token[1:]:
                mapped = short_map.get(char)
                if mapped:
                    state.toggle(mapped)


def _split_path_and_flags(tokens: list[str]) -> tuple[list[str], list[str]]:
    # Treat leading flags and trailing toggles uniformly; Windows paths don't start with '-'
    path_tokens: list[str] = []
    flag_tokens: list[str] = []
    for token in tokens:
        if token.startswith('-'):
            flag_tokens.append(token)
            continue
        path_tokens.append(token)
    return path_tokens, flag_tokens


def _print_interactive_status(state: LaunchState) -> None:
    active_flags = _format_active_flags(state)
    current_directory = state.directory or "<not set>"
    print(
        Fore.CYAN
        + f"\nCurrent directory: {current_directory}\nActive flags: {active_flags}"
        + Style.RESET_ALL
    )


def _apply_composite_command(parts: list[str], state: LaunchState) -> bool:
    # Returns True if a path was supplied, so the caller can short-circuit the default handler
    if not parts:
        return False
    path_tokens, flag_tokens = _split_path_and_flags(parts)
    if flag_tokens:
        _apply_flag_string(" ".join(flag_tokens), state)
    if path_tokens:
        state.directory = sanitize_path(" ".join(path_tokens))
        return True
    return False


def interactive_configure(args: Namespace) -> Namespace:
    state = LaunchState(
        directory=sanitize_path(args.directory) if args.directory else "",
        verbose=args.verbose,
        no_lzx=args.no_lzx,
        force_lzx=args.force_lzx,
        thorough=args.thorough,
        brand_files=args.brand_files,
        single_worker=getattr(args, 'single_worker', False),
    )

    print(Fore.YELLOW + "\nInteractive launch detected. Configure your run before starting." + Style.RESET_ALL)
    _print_flag_reference()
    while True:
        _print_interactive_status(state)
        print(
            "Enter a directory path (optionally add flags like '-vx'),"
            " or use [S]tart to proceed and [F]lag help for tips."
        )
        try:
            command = read_user_input("> ").strip()
        except (KeyboardInterrupt, EscapeExit):
            announce_cancelled()
            raise SystemExit(0)

        command = command or 's'
        lowered = command.lower()

        if lowered in {'s', 'start'}:
            if not state.directory:
                print(Fore.RED + "Directory is required before starting." + Style.RESET_ALL)
                continue
            if not os.path.exists(state.directory):
                print(
                    Fore.RED
                    + f"Directory '{state.directory}' was not found."
                    + Style.RESET_ALL
                )
                continue
            break

        if lowered in {'f', 'flags'}:
            print(
                "Toggle flags by entering their short forms together (e.g. -vx)"
                " or separately (e.g. -t). Re-enter a flag to disable it."
            )
            _print_flag_reference()
            continue

        if command.startswith('-'):
            _apply_flag_string(command, state)
            continue

        try:
            parts = shlex.split(command, posix=False)
        except ValueError:
            parts = []

        if _apply_composite_command(parts, state):
            continue

        state.directory = sanitize_path(command)

    args.directory = state.directory
    args.verbose = state.verbose
    args.no_lzx = state.no_lzx
    args.force_lzx = state.force_lzx
    args.thorough = state.thorough
    args.brand_files = state.brand_files
    args.single_worker = state.single_worker
    return args


def acquire_directory(args: Namespace, interactive_launch: bool) -> tuple[str, Namespace]:
    while True:
        candidate = sanitize_path(args.directory) if args.directory else ""
        if candidate and os.path.exists(candidate):
            return candidate, args

        if candidate:
            print(Fore.RED + f"Directory '{candidate}' does not exist." + Style.RESET_ALL)
        else:
            print(Fore.RED + "No directory provided." + Style.RESET_ALL)

        if interactive_launch:
            args.directory = ""
            args = interactive_configure(args)
        else:
            try:
                args.directory = resolve_directory(None)
            except EscapeExit:
                announce_cancelled()
                raise SystemExit(0)
            except KeyboardInterrupt:
                announce_cancelled()
                raise SystemExit(0)
