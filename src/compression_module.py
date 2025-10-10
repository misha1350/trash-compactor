import os
from pathlib import Path

from .compression.compression_executor import execute_compression_plan, legacy_compress_file
from .compression.compression_planner import iter_files, plan_compression
from .config import DEFAULT_MIN_SAVINGS_PERCENT, clamp_savings_percent
from .skip_logic import log_directory_skips
from .stats import CompressionStats, LegacyCompressionStats
from .timer import PerformanceMonitor
from .workers import lzx_worker_count, set_worker_cap, xp_worker_count


def compress_directory(
    directory_path: str,
    verbosity: int = 0,
    thorough_check: bool = False,
    min_savings_percent: float = DEFAULT_MIN_SAVINGS_PERCENT,
) -> tuple[CompressionStats, PerformanceMonitor]:
    import logging

    stats = CompressionStats()
    monitor = PerformanceMonitor()
    monitor.start_operation()

    min_savings_percent = clamp_savings_percent(min_savings_percent)

    base_dir = Path(directory_path).resolve()
    if thorough_check:
        logging.info("Using thorough checking mode - this will be slower but more accurate for previously compressed files")

    all_files = list(iter_files(base_dir, stats, verbosity, min_savings_percent))
    total_files = len(all_files)
    monitor.stats.total_files = total_files

    log_directory_skips(stats, verbosity, min_savings_percent)

    if all_files:
        plan = plan_compression(all_files, stats, monitor, thorough_check)
        if plan:
            xp_workers = xp_worker_count()
            lzx_workers = lzx_worker_count()
            execute_compression_plan(plan, stats, monitor, verbosity >= 4, xp_workers, lzx_workers)

    monitor.stats.files_compressed = stats.compressed_files
    monitor.end_operation()
    return stats, monitor


def compress_directory_legacy(directory_path: str, thorough_check: bool = False) -> LegacyCompressionStats:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    stats = LegacyCompressionStats()
    base_dir = Path(directory_path).resolve()

    print(f"\nChecking files in {directory_path} for proper compression branding...")
    if thorough_check:
        print("Using thorough checking mode - this will be slower but more accurate")

    from .config import get_cpu_info
    from .workers import _apply_worker_cap

    physical_cores, _ = get_cpu_info()
    default_workers = max(physical_cores or 1, 1)
    worker_count = _apply_worker_cap(default_workers)
    if worker_count == default_workers:
        print(f"Using {worker_count} parallel workers to maximize performance\n")
    else:
        noun = "worker" if worker_count == 1 else "workers"
        print(f"Using {worker_count} {noun} due to storage throttling hints\n")

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
                    from .file_utils import is_file_compressed
                    is_compressed, _ = is_file_compressed(file_path, thorough_check=False)
                    if is_compressed:
                        stats.branded_files += 1
                    else:
                        stats.still_unmarked += 1
                        print(f"WARNING: File still not recognized as compressed: {relative_path}")
                else:
                    print(f"ERROR: Failed branding file: {relative_path}")
            except (OSError, ValueError) as exc:
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
    from .config import MIN_COMPRESSIBLE_SIZE, SKIP_EXTENSIONS
    from .file_utils import is_file_compressed

    targets = []
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
            except (OSError, ValueError) as exc:
                stats.errors.append(f"Error checking file {file_path}: {exc}")
    return targets