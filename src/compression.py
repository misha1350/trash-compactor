import ctypes
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterator, Optional, Sequence

from .config import (
    COMPRESSION_ALGORITHMS,
    MIN_COMPRESSIBLE_SIZE,
    SKIP_EXTENSIONS,
    get_cpu_info,
)
from .file_utils import get_size_category, is_file_compressed, should_compress_file
from .stats import CompressionStats, LegacyCompressionStats, Spinner
from .timer import PerformanceMonitor


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def _run_compact(command: str, *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        startupinfo=_hidden_startupinfo(),
        shell=True,
        text=capture,
    )


def compress_file(file_path: Path, algorithm: str) -> bool:
    try:
        command = fr'compact /c /a /exe:{algorithm} "{file_path.resolve()}"'
        result = _run_compact(command)
        return result.returncode == 0
    except Exception as exc:
        logging.error("Error compressing %s: %s", file_path, exc)
        return False


def legacy_compress_file(file_path: Path) -> bool:
    try:
        command = fr'compact /c "{Path(file_path).resolve()}"'
        result = _run_compact(command, capture=True)
        logging.debug("Command: %s", command)
        logging.debug("Output: %s", result.stdout)
        return result.returncode == 0
    except Exception as exc:
        logging.error("Error branding %s: %s", file_path, exc)
        return False


def get_compressed_size(file_path: Path) -> int:
    getter = ctypes.windll.kernel32.GetCompressedFileSizeW
    getter.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    getter.restype = ctypes.c_ulong

    high = ctypes.c_ulong(0)
    low = getter(str(file_path), ctypes.byref(high))
    if low == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
    return (high.value << 32) + low


def compress_directory(directory_path: str, verbose: bool = False, thorough_check: bool = False) -> tuple[CompressionStats, PerformanceMonitor]:
    stats = CompressionStats()
    monitor = PerformanceMonitor()
    monitor.start_operation()

    base_dir = Path(directory_path).resolve()
    if thorough_check:
        logging.info("Using thorough checking mode - this will be slower but more accurate for previously compressed files")

    all_files = list(_iter_files(base_dir))
    total_files = len(all_files)
    monitor.stats.total_files = total_files

    spinner = None
    if not verbose:
        spinner = Spinner()
        spinner.start(total=total_files)

    plan = _plan_compression(all_files, stats, monitor, thorough_check)
    monitor.stats.files_skipped = stats.skipped_files

    if plan:
        _execute_plan(
            plan,
            stats,
            monitor,
            spinner,
            verbose,
            base_dir,
        )

    monitor.stats.files_compressed = stats.compressed_files

    if spinner and not verbose:
        spinner.stop()

    monitor.end_operation()
    return stats, monitor


def _iter_files(root: Path) -> Iterator[Path]:
    for current_root, _, files in os.walk(root):
        current_base = Path(current_root)
        for name in files:
            yield current_base / name


def _plan_compression(
    files: Sequence[Path],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    thorough_check: bool,
) -> list[tuple[Path, int, str]]:
    candidates: list[tuple[Path, int, str]] = []
    with monitor.time_file_scan():
        for file_path in files:
            try:
                should_compress, reason, current_size = should_compress_file(file_path, thorough_check)
                file_size = file_path.stat().st_size
                stats.total_original_size += file_size

                if should_compress:
                    algorithm = COMPRESSION_ALGORITHMS[get_size_category(file_size)]
                    candidates.append((file_path, file_size, algorithm))
                else:
                    stats.skipped_files += 1
                    stats.total_compressed_size += current_size
                    if "already compressed" in reason.lower():
                        stats.already_compressed_files += 1
                    logging.debug("Skipping %s: %s", file_path, reason)
            except Exception as exc:
                # Keep marching even when stat calls misbehave on a single file
                stats.errors.append(f"Error processing {file_path}: {exc}")
                stats.skipped_files += 1
                try:
                    stats.total_compressed_size += file_path.stat().st_size
                except Exception:
                    pass
                logging.error("Error processing %s: %s", file_path, exc)
    return candidates


def _xp_worker_count() -> int:
    _, logical = get_cpu_info()
    threads = logical
    if not threads:
        return 1

    # Keep one thread free so the shell and I/O threads stay responsive
    return max(1, threads - 1)


def _lzx_worker_count() -> int:
    physical, _ = get_cpu_info()
    cores = physical
    if not cores or cores <= 4:
        return 1

    # LZX saturates well with two worker processes on CPUs with 6 cores or more
    return 2

def _execute_plan(
    plan: Sequence[tuple[Path, int, str]],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    spinner: Optional[Spinner],
    verbose: bool,
    base_dir: Path,
) -> None:
    total = len(plan)
    if not total:
        return

    update_interval = max(1, total // 100)
    base_dir_str = str(base_dir)
    processed = 0

    def _process(entries: Sequence[tuple[Path, int, str]], workers: int) -> None:
        nonlocal processed
        if not entries:
            return

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_compress_single_file, path, size, algorithm): (path, size, algorithm)
                for path, size, algorithm in entries
            }

            for future in as_completed(futures):
                file_path, file_size, algorithm = futures[future]
                processed += 1

                if spinner and not verbose and processed % update_interval == 0:
                    formatted_path = spinner.format_path(str(file_path), base_dir_str)
                    spinner.update(processed, formatted_path)

                try:
                    with monitor.time_compression():
                        success, compressed_size = future.result()

                    if success:
                        stats.compressed_files += 1
                        stats.total_compressed_size += compressed_size
                        logging.debug("Compressed %s using %s", file_path, algorithm)
                    else:
                        stats.skipped_files += 1
                        stats.total_compressed_size += file_size
                        logging.debug("Compression failed for %s using %s", file_path, algorithm)
                except Exception as exc:
                    stats.errors.append(f"Error compressing {file_path}: {exc}")
                    stats.skipped_files += 1
                    stats.total_compressed_size += file_size
                    logging.error("Error compressing %s: %s", file_path, exc)

    xp_entries = [entry for entry in plan if entry[2] != 'LZX']
    lzx_entries = [entry for entry in plan if entry[2] == 'LZX']

    _process(xp_entries, _xp_worker_count())
    _process(lzx_entries, _lzx_worker_count())

    monitor.stats.files_skipped = stats.skipped_files


def _compress_single_file(file_path: Path, file_size: int, algorithm: str) -> tuple[bool, int]:
    if compress_file(file_path, algorithm):
        _, compressed_size = is_file_compressed(file_path, thorough_check=False)
        return True, compressed_size
    return False, file_size


def compress_directory_legacy(directory_path: str, thorough_check: bool = False) -> LegacyCompressionStats:
    stats = LegacyCompressionStats()
    base_dir = Path(directory_path).resolve()

    print(f"\nChecking files in {directory_path} for proper compression branding...")
    if thorough_check:
        print("Using thorough checking mode - this will be slower but more accurate")

    physical_cores, _ = get_cpu_info()
    worker_count = max(physical_cores or 1, 1)
    print(f"Using {worker_count} parallel workers to maximize performance\n")

    targets = _collect_branding_targets(base_dir, stats, thorough_check)
    if not targets:
        print("No files need branding - all eligible files are already marked as compressed.")
        return stats

    print(f"Found {len(targets)} files that need branding...")
    base_dir_str = str(base_dir)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_file = {executor.submit(legacy_compress_file, path): path for path in targets}
        total = len(targets)

        for completed, future in enumerate(as_completed(future_to_file), start=1):
            file_path = future_to_file[future]
            relative_path = os.path.relpath(str(file_path), base_dir_str)

            if completed % 10 == 0 or completed == total:
                print(f"Progress: {completed}/{total} files processed ({completed / total * 100:.1f}%)")

            try:
                result = future.result()
                if result:
                    is_compressed, _ = is_file_compressed(file_path, thorough_check=False)
                    if is_compressed:
                        stats.branded_files += 1
                    else:
                        stats.still_unmarked += 1
                        print(f"WARNING: File still not recognized as compressed: {relative_path}")
                else:
                    print(f"ERROR: Failed branding file: {relative_path}")
            except Exception as exc:
                stats.errors.append(f"Exception for {file_path}: {exc}")
                print(f"ERROR: Exception {exc} while branding file: {relative_path}")

    print(f"\nBranding complete. Successfully branded {stats.branded_files} files.")
    if stats.still_unmarked:
        print(f"Warning: {stats.still_unmarked} files could not be properly marked as compressed.")

    return stats


def _collect_branding_targets(
    base_dir: Path,
    stats: LegacyCompressionStats,
    thorough_check: bool,
) -> list[Path]:
    targets: list[Path] = []
    for root, _, files in os.walk(base_dir):
        for name in files:
            file_path = Path(root) / name
            stats.total_files += 1

            if file_path.suffix.lower() in SKIP_EXTENSIONS:
                continue

            try:
                if file_path.stat().st_size < MIN_COMPRESSIBLE_SIZE:
                    continue

                is_compressed, _ = is_file_compressed(file_path, thorough_check)
                if not is_compressed:
                    targets.append(file_path)
            except Exception as exc:
                stats.errors.append(f"Error checking file {file_path}: {exc}")
    return targets