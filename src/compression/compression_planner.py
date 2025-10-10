import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Iterator, Optional

from ..config import COMPRESSION_ALGORITHMS, get_cpu_info
from ..file_utils import should_compress_file
from ..skip_logic import maybe_skip_directory
from ..stats import CompressionStats
from ..timer import PerformanceMonitor
from ..workers import entropy_worker_count


def iter_files(root: Path, stats: CompressionStats, verbosity: int, min_savings_percent: float) -> Iterator[Path]:
    collect_entropy = True
    executor = None
    if collect_entropy:
        worker_count = entropy_worker_count()
        if worker_count > 0:
            executor = ThreadPoolExecutor(max_workers=worker_count)

    try:
        skip_root = maybe_skip_directory(
            root,
            root,
            stats,
            collect_entropy,
            min_savings_percent,
            verbosity,
        ).skip
        if skip_root:
            return

        for current_root, dirnames, files in os.walk(root):
            current_base = Path(current_root)

            pending = []
            new_dirnames = []

            for name in dirnames:
                candidate = current_base / name
                decision = maybe_skip_directory(
                    candidate,
                    root,
                    stats,
                    collect_entropy,
                    min_savings_percent,
                    verbosity,
                )
                if decision.skip:
                    continue
                new_dirnames.append(name)

            dirnames[:] = new_dirnames

            for name in files:
                yield current_base / name
    finally:
        if executor is not None:
            executor.shutdown(wait=True)


def plan_compression(
    files: Iterator[Path],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    thorough_check: bool,
) -> list[tuple[Path, int, str]]:
    candidates = []
    with monitor.time_file_scan():
        for file_path in files:
            try:
                decision = should_compress_file(file_path, thorough_check)
                file_size = file_path.stat().st_size
                stats.total_original_size += file_size

                if decision.should_compress:
                    algorithm = COMPRESSION_ALGORITHMS[get_size_category(file_size)]
                    candidates.append((file_path, file_size, algorithm))
                else:
                    stats.skipped_files += 1
                    resolved_size = decision.size_hint or file_size
                    stats.total_compressed_size += resolved_size
                    stats.total_skipped_size += file_size
                    reason = decision.reason
                    if "already compressed" in reason.lower():
                        stats.already_compressed_files += 1
                    logging.debug("Skipping %s: %s", file_path, reason)
            except OSError as exc:
                stats.errors.append(f"Error processing {file_path}: {exc}")
                stats.skipped_files += 1
                try:
                    file_size_fallback = file_path.stat().st_size
                    stats.total_compressed_size += file_size_fallback
                    stats.total_skipped_size += file_size_fallback
                except OSError:
                    pass
                logging.error("Error processing %s: %s", file_path, exc)
    return candidates


def get_size_category(file_size: int) -> str:
    from ..config import SIZE_THRESHOLDS
    from bisect import bisect_right

    breaks, labels = zip(*SIZE_THRESHOLDS)
    index = bisect_right(breaks, file_size)
    return labels[index] if index < len(labels) else 'large'