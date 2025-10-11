import logging
import os
from pathlib import Path
from typing import Iterable, Iterator, Optional

from ..config import COMPRESSION_ALGORITHMS
from ..file_utils import should_compress_file
from ..skip_logic import append_directory_skip_record, evaluate_entropy_directory, maybe_skip_directory
from ..stats import CompressionStats, DirectorySkipRecord
from ..timer import PerformanceMonitor


def iter_files(
    root: Path,
    stats: CompressionStats,
    verbosity: int,
    min_savings_percent: float,
    collect_entropy: bool,
) -> Iterator[Path]:
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


def plan_compression(
    files: Iterable[Path],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    thorough_check: bool,
    *,
    base_dir: Path,
    min_savings_percent: float,
    verbosity: int,
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
                    reason = decision.reason
                    resolved_size = decision.size_hint or file_size
                    stats.record_file_skip(
                        file_path,
                        reason,
                        resolved_size,
                        file_size,
                        already_compressed="already compressed" in reason.lower(),
                    )
                    logging.debug("Skipping %s: %s", file_path, reason)
            except OSError as exc:
                stats.errors.append(f"Error processing {file_path}: {exc}")
                try:
                    file_size_fallback = file_path.stat().st_size
                except OSError:
                    file_size_fallback = 0
                stats.record_file_skip(
                    file_path,
                    f"Error processing file: {exc}",
                    file_size_fallback,
                    file_size_fallback,
                )
                logging.error("Error processing %s: %s", file_path, exc)
        candidates = _filter_high_entropy_directories(
            candidates,
            base_dir=base_dir,
            stats=stats,
            min_savings_percent=min_savings_percent,
            verbosity=verbosity,
        )
    return candidates


def get_size_category(file_size: int) -> str:
    from ..config import SIZE_THRESHOLDS
    from bisect import bisect_right

    breaks, labels = zip(*SIZE_THRESHOLDS)
    index = bisect_right(breaks, file_size)
    return labels[index] if index < len(labels) else 'large'


def _filter_high_entropy_directories(
    candidates: list[tuple[Path, int, str]],
    *,
    base_dir: Path,
    stats: CompressionStats,
    min_savings_percent: float,
    verbosity: int,
) -> list[tuple[Path, int, str]]:
    if not candidates or min_savings_percent <= 0:
        return candidates

    directories = {path.parent for path, _, _ in candidates}
    directories.add(base_dir)

    skipped_directories: dict[Path, DirectorySkipRecord] = {}

    for directory in sorted(directories, key=lambda item: (len(item.parts), str(item).casefold())):
        if _has_skipped_ancestor(directory, base_dir, skipped_directories):
            continue

        record = evaluate_entropy_directory(directory, base_dir, min_savings_percent, verbosity)
        if record:
            append_directory_skip_record(stats, record)
            skipped_directories[directory] = record

    if not skipped_directories:
        return candidates

    filtered: list[tuple[Path, int, str]] = []
    for path, file_size, algorithm in candidates:
        skip_record = _locate_skip_record(path.parent, base_dir, skipped_directories)
        if skip_record is not None:
            stats.record_file_skip(path, skip_record.reason, file_size, file_size)
            logging.debug("Skipping %s due to %s", path, skip_record.reason)
            continue
        filtered.append((path, file_size, algorithm))

    return filtered


def _has_skipped_ancestor(
    directory: Path,
    base_dir: Path,
    skipped: dict[Path, DirectorySkipRecord],
) -> bool:
    for ancestor in _ancestors_including_base(directory, base_dir):
        if ancestor in skipped:
            return True
    return False


def _locate_skip_record(
    directory: Path,
    base_dir: Path,
    skipped: dict[Path, DirectorySkipRecord],
) -> Optional[DirectorySkipRecord]:
    for ancestor in _ancestors_including_base(directory, base_dir):
        if ancestor in skipped:
            return skipped[ancestor]
    return None


def _ancestors_including_base(path: Path, base_dir: Path) -> list[Path]:
    ancestors: list[Path] = []
    current = path
    while True:
        ancestors.append(current)
        if current == base_dir:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return ancestors

