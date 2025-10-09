import ctypes
import logging
import math
import os
import subprocess
import sys
import threading
import time
from collections import Counter, OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Optional, Sequence

try:
    from colorama import Fore, Style  # type: ignore
except ImportError:  # pragma: no cover - colour output is optional
    class _ColorFallback:
        GREEN = ""
        YELLOW = ""
        RESET_ALL = ""

    Fore = Style = _ColorFallback()  # type: ignore

from .config import (
    COMPRESSION_ALGORITHMS,
    MIN_COMPRESSIBLE_SIZE,
    SKIP_EXTENSIONS,
    get_cpu_info,
)
from .file_utils import get_size_category, is_file_compressed, should_compress_file, should_skip_directory
from .stats import CompressionStats, DirectorySkipRecord, LegacyCompressionStats, Spinner
from .timer import PerformanceMonitor

_BATCH_SIZE = 100
_MAX_COMMAND_CHARS = 4000

_WORKER_CAP: ContextVar[Optional[int]] = ContextVar("worker_cap", default=None)


def set_worker_cap(limit: Optional[int]) -> None:
    if limit is not None and limit < 1:
        raise ValueError("worker cap must be >= 1")
    _WORKER_CAP.set(limit)


def _apply_worker_cap(default: int) -> int:
    limit = _WORKER_CAP.get()
    if limit is None:
        return default
    return max(1, min(default, limit))


_CACHE_TERMINALS: tuple[str, ...] = (
    'cache',
    'cache2',
    'cache_data',
    'cachedata',
    'media cache',
    'code cache',
    'gpu cache',
    'cache storage',
    'cache_storage',
    'shadercache',
)

_CACHE_ROOT_MARKERS: tuple[str, ...] = (
    'appdata',
    'programdata',
    'locallow',
    'localcache',
    'localappdata',
    'users',
    'temp',
)

_CACHE_HINTS: tuple[str, ...] = (
    'chrome',
    'chromium',
    'brave',
    'edge',
    'electron',
    'discord',
    'teams',
    'steam',
    'telegram',
    'whatsapp',
    'slack',
    'vivaldi',
    'opera',
    'githubdesktop',
    'riot',
    'epic',
    'zoom',
    'spotify',
    'firefox',
    'mozilla',
)


def _relative_to_base(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _cache_directory_reason(path: Path) -> Optional[str]:
    parts = path.parts
    parts_cf = [segment.casefold() for segment in parts]
    if len(parts_cf) <= 2:
        return None

    terminal_hint: Optional[str] = None
    for candidate in parts_cf[-2:]:
        for keyword in _CACHE_TERMINALS:
            if keyword in candidate:
                terminal_hint = keyword
                break
        if terminal_hint:
            break

    if terminal_hint is None:
        return None

    if not any(marker in parts_cf for marker in _CACHE_ROOT_MARKERS):
        return None

    hint: Optional[str] = None
    for original, lowered in zip(parts, parts_cf):
        for token in _CACHE_HINTS:
            if token in lowered:
                hint = original
                break
        if hint:
            break

    descriptor = hint or parts[-1]
    return f"{descriptor} cache directory"


def _shannon_entropy(sample: bytes) -> float:
    if not sample:
        return 0.0
    total = len(sample)
    frequencies = Counter(sample)
    entropy = 0.0
    for count in frequencies.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def _sample_directory_entropy(
    path: Path,
    max_files: int = 24,
    chunk_size: int = 65536,
    max_bytes: int = 4 * 1024 * 1024,
) -> tuple[Optional[float], int, int]:
    pending = deque([path])
    sampled_files = 0
    sampled_bytes = 0
    weighted_entropy = 0.0

    while pending and sampled_files < max_files and sampled_bytes < max_bytes:
        current = pending.popleft()
        try:
            entries = list(current.iterdir())
        except OSError as exc:
            logging.debug("Unable to inspect %s for entropy: %s", current, exc)
            continue

        for entry in entries:
            if entry.is_dir():
                pending.append(entry)
                continue

            try:
                with entry.open('rb') as stream:
                    data = stream.read(chunk_size)
            except OSError as exc:
                logging.debug("Unable to sample %s for entropy: %s", entry, exc)
                continue

            if not data:
                continue

            entropy = _shannon_entropy(data)
            length = len(data)
            sampled_files += 1
            sampled_bytes += length
            weighted_entropy += entropy * length

            if sampled_files >= max_files or sampled_bytes >= max_bytes:
                break

        if sampled_files >= max_files or sampled_bytes >= max_bytes:
            break

    if sampled_bytes == 0:
        return None, sampled_files, sampled_bytes

    average_entropy = weighted_entropy / sampled_bytes
    return average_entropy, sampled_files, sampled_bytes


def _evaluate_cache_directory(directory: Path, base_dir: Path, collect_entropy: bool) -> Optional[DirectorySkipRecord]:
    reason = _cache_directory_reason(directory)
    if reason is None:
        return None

    average_entropy = None
    sampled_files = 0
    sampled_bytes = 0
    if collect_entropy:
        average_entropy, sampled_files, sampled_bytes = _sample_directory_entropy(directory)

    return DirectorySkipRecord(
        path=str(directory),
        relative_path=_relative_to_base(directory, base_dir),
        reason=reason,
        category='cache',
        average_entropy=average_entropy,
        sampled_files=sampled_files,
        sampled_bytes=sampled_bytes,
    )


def _maybe_skip_directory(directory: Path, base_dir: Path, stats: CompressionStats, collect_entropy: bool) -> bool:
    skip, reason = should_skip_directory(directory)
    if skip:
        stats.directory_skips.append(
            DirectorySkipRecord(
                path=str(directory),
                relative_path=_relative_to_base(directory, base_dir),
                reason=reason or "Excluded system directory",
                category='system',
            )
        )
        logging.debug("Skipping system directory %s: %s", directory, reason)
        return True

    cache_record = _evaluate_cache_directory(directory, base_dir, collect_entropy)
    if cache_record:
        stats.directory_skips.append(cache_record)
        logging.debug("Skipping cache directory %s: %s", directory, cache_record.reason)
        return True

    return False


def _log_directory_skips(stats: CompressionStats, verbosity: int) -> None:
    if verbosity < 1:
        return

    cache_records = [record for record in stats.directory_skips if record.category == 'cache']
    if not cache_records:
        return

    logging.info("Skipped %s cache directories (entropy in bits/byte):", len(cache_records))
    for record in cache_records:
        if record.average_entropy is not None:
            logging.info(
                " - %s - %s (entropy %.2f across %s files)",
                record.relative_path,
                record.reason,
                record.average_entropy,
                record.sampled_files,
            )
        else:
            logging.info(" - %s - %s", record.relative_path, record.reason)


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


def compress_directory(directory_path: str, verbosity: int = 0, thorough_check: bool = False) -> tuple[CompressionStats, PerformanceMonitor]:
    stats = CompressionStats()
    monitor = PerformanceMonitor()
    monitor.start_operation()

    base_dir = Path(directory_path).resolve()
    if thorough_check:
        logging.info("Using thorough checking mode - this will be slower but more accurate for previously compressed files")

    all_files = list(_iter_files(base_dir, stats, verbosity))
    total_files = len(all_files)
    monitor.stats.total_files = total_files

    _log_directory_skips(stats, verbosity)

    debug_output = verbosity >= 4
    spinner_enabled = verbosity == 0

    spinner: Optional[Spinner] = None
    if spinner_enabled:
        spinner = Spinner()
        spinner.set_label("Scanning files...")
        spinner.start(total=total_files)
        spinner.update(0, "")

    plan = _plan_compression(all_files, stats, monitor, thorough_check, spinner, debug_output)
    monitor.stats.files_skipped = stats.skipped_files

    if spinner:
        final_skip_message = f"Skipped {stats.skipped_files}/{total_files} poorly compressible files"
        spinner.stop(final_message=final_skip_message)
        spinner = None

    if plan:
        _execute_plan(
            plan,
            stats,
            monitor,
            debug_output,
        )

    monitor.stats.files_compressed = stats.compressed_files

    monitor.end_operation()
    return stats, monitor


def _iter_files(root: Path, stats: CompressionStats, verbosity: int) -> Iterator[Path]:
    collect_entropy = verbosity >= 1
    for current_root, dirnames, files in os.walk(root):
        current_base = Path(current_root)

        for index in range(len(dirnames) - 1, -1, -1):
            candidate = current_base / dirnames[index]
            if _maybe_skip_directory(candidate, root, stats, collect_entropy):
                del dirnames[index]

        for name in files:
            yield current_base / name


def _plan_compression(
    files: Sequence[Path],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    thorough_check: bool,
    spinner: Optional[Spinner],
    debug_output: bool,
) -> list[tuple[Path, int, str]]:
    candidates: list[tuple[Path, int, str]] = []
    with monitor.time_file_scan():
        for index, file_path in enumerate(files, start=1):
            if spinner and not debug_output:
                spinner.update(index)
            try:
                should_compress, reason, current_size = should_compress_file(file_path, thorough_check)
                file_size = file_path.stat().st_size
                stats.total_original_size += file_size

                if should_compress:
                    algorithm = COMPRESSION_ALGORITHMS[get_size_category(file_size)]
                    candidates.append((file_path, file_size, algorithm))
                else:
                    stats.skipped_files += 1
                    resolved_size = current_size if current_size else file_size
                    stats.total_compressed_size += resolved_size
                    stats.total_skipped_size += file_size
                    if "already compressed" in reason.lower():
                        stats.already_compressed_files += 1
                    logging.debug("Skipping %s: %s", file_path, reason)
            except Exception as exc:
                # Keep marching even when stat calls misbehave on a single file
                stats.errors.append(f"Error processing {file_path}: {exc}")
                stats.skipped_files += 1
                try:
                    file_size_fallback = file_path.stat().st_size
                    stats.total_compressed_size += file_size_fallback
                    stats.total_skipped_size += file_size_fallback
                except Exception:
                    pass
                logging.error("Error processing %s: %s", file_path, exc)
    return candidates


def _xp_worker_count() -> int:
    _, logical = get_cpu_info()
    threads = logical
    if not threads:
        return _apply_worker_cap(1)

    # Keep one thread free so the shell and I/O threads stay responsive
    default = max(1, threads - 1)
    return _apply_worker_cap(default)


def _lzx_worker_count() -> int:
    physical, logical = get_cpu_info()
    cores = physical or logical
    if not cores or cores <= 4:
        return _apply_worker_cap(1)

    # LZX saturates well with two worker processes on CPUs with 6 cores or more
    return _apply_worker_cap(2)

def _execute_plan(
    plan: Sequence[tuple[Path, int, str]],
    stats: CompressionStats,
    monitor: PerformanceMonitor,
    debug_output: bool,
) -> None:
    total = len(plan)
    if not total:
        return

    def _chunk(entries: Sequence[tuple[Path, int]], size: int) -> list[list[tuple[Path, int]]]:
        batches: list[list[tuple[Path, int]]] = []
        current: list[tuple[Path, int]] = []
        current_length = 0

        for path, file_size in entries:
            path_length = len(str(path.resolve())) + 3  # keep CreateProcess payload under limits
            if current and (len(current) >= size or current_length + path_length > _MAX_COMMAND_CHARS):
                batches.append(current)
                current = []
                current_length = 0

            current.append((path, file_size))
            current_length += path_length

        if current:
            batches.append(current)

        return batches

    def _compact_batch(algo: str, paths: Sequence[Path]) -> subprocess.CompletedProcess:
        quoted = " ".join(f'"{path.resolve()}"' for path in paths)
        return _run_compact(f'compact /c /a /exe:{algo} {quoted}')

    def _record_success(path: Path, compressed_size: int, algo: str, verified: bool) -> None:
        stats.compressed_files += 1
        stats.total_compressed_size += compressed_size
        if verified:
            logging.debug("Compressed %s using %s", path, algo)
        else:
            logging.debug(
                "Compressed %s using %s (verification reported no size change; trusting compact return)",
                path,
                algo,
            )

    def _record_failure(path: Path, file_size: int, algo: str, reason: Optional[str] = None) -> None:
        stats.skipped_files += 1
        stats.total_compressed_size += file_size
        stats.total_skipped_size += file_size
        if reason:
            logging.debug("Compression skipped for %s using %s: %s", path, algo, reason)
        else:
            logging.debug("Compression failed for %s using %s", path, algo)

    def _finalize_success(path: Path, fallback_size: int, algo: str, context: str) -> None:
        try:
            verified, compressed_size = is_file_compressed(path, thorough_check=False)
        except Exception as exc:  # pragma: no cover - defensive
            stats.errors.append(f"Error verifying {path}: {exc}")
            logging.error("Error verifying %s after %s compression: %s", path, context, exc)
            _record_success(path, fallback_size, algo, verified=False)
        else:
            _record_success(path, compressed_size, algo, verified)

    def _compress_single(path: Path, file_size: int, algo: str) -> None:
        with monitor.time_compression():
            success = compress_file(path, algo)

        if not success:
            _record_failure(path, file_size, algo)
            return

        _finalize_success(path, file_size, algo, context='fallback')

    def _process_group(algo: str, entries: Sequence[tuple[Path, int]], workers: int, stage_idx: int) -> None:
        if not entries:
            return

        progress = stage_progress[stage_idx]

        def _advance(count: int) -> None:
            if count <= 0:
                return
            if debug_output:
                progress['processed'] = min(progress['processed'] + count, progress['total'])
                return
            with render_lock:
                progress['processed'] = min(progress['processed'] + count, progress['total'])

        batches = _chunk(entries, _BATCH_SIZE)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _compact_batch,
                    algo,
                    [path for path, _ in batch],
                ): batch
                for batch in batches
            }

            for future in as_completed(futures):
                batch = futures[future]

                try:
                    with monitor.time_compression():
                        result = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    logging.error(
                        "Batch compression exception (%s files, algo=%s): %s. Retrying individually.",
                        len(batch),
                        algo,
                        exc,
                    )
                    for path, file_size in batch:
                        stats.errors.append(f"Batch exception for {path}: {exc}")
                        _compress_single(path, file_size, algo)
                        _advance(1)
                    continue

                if result.returncode != 0:
                    logging.debug(
                        "Batch compact returned %s for %s with %s files. Falling back to single-file attempts.",
                        result.returncode,
                        algo,
                        len(batch),
                    )
                    for path, file_size in batch:
                        _compress_single(path, file_size, algo)
                        _advance(1)
                    continue

                for path, file_size in batch:
                    _finalize_success(path, file_size, algo, context='batch')
                _advance(len(batch))

    grouped: OrderedDict[str, list[tuple[Path, int]]] = OrderedDict()
    for path, size, algorithm in plan:
        grouped.setdefault(algorithm, []).append((path, size))

    stage_items = list(grouped.items())
    stage_states: list[str] = ['pending'] * len(stage_items)
    stage_progress = [{'processed': 0, 'total': len(entries)} for _, entries in stage_items]
    render_lock = threading.Lock()
    rendered_lines = 0
    render_initialized = False
    stop_render = threading.Event()

    def _render_stage_statuses() -> None:
        nonlocal rendered_lines, render_initialized
        if debug_output or not stage_items:
            return

        spinner_chars = ['\\', '|', '/', '-']
        spinner_idx = int(time.time() * 2) % len(spinner_chars)

        lines: list[str] = []
        for idx, (state, (algo, entries)) in enumerate(zip(stage_states, stage_items)):
            total = stage_progress[idx]['total']
            processed = min(stage_progress[idx]['processed'], total)
            if state == 'done':
                lines.append(Fore.GREEN + f"Compressing {total} files with {algo}... done" + Style.RESET_ALL)
            elif state == 'running':
                lines.append(
                    Fore.YELLOW
                    + f"{spinner_chars[spinner_idx]} Compressing {processed}/{total} files with {algo}..."
                    + Style.RESET_ALL
                )
            else:
                lines.append(f"Pending {total} files for {algo} compression.")

        if not render_initialized:
            sys.stdout.write("\n" * len(lines))
            sys.stdout.flush()
            render_initialized = True
            rendered_lines = len(lines)

        if rendered_lines:
            sys.stdout.write("\033[F" * rendered_lines)
        for line in lines:
            sys.stdout.write("\r" + line + "\033[K\n")
        sys.stdout.flush()
        rendered_lines = len(lines)

    def _render_loop() -> None:
        while not stop_render.is_set():
            with render_lock:
                _render_stage_statuses()
            time.sleep(0.2)
        with render_lock:
            _render_stage_statuses()

    render_thread: Optional[threading.Thread] = None

    try:
        if not debug_output and stage_items:
            render_thread = threading.Thread(target=_render_loop, daemon=True)
            render_thread.start()

        for idx, (algorithm, entries) in enumerate(stage_items):
            if not debug_output:
                with render_lock:
                    stage_states[idx] = 'running'

            if algorithm == 'LZX':
                _process_group(algorithm, entries, _lzx_worker_count(), idx)
            else:
                _process_group(algorithm, entries, _xp_worker_count(), idx)

            if not debug_output:
                with render_lock:
                    stage_states[idx] = 'done'
                    stage_progress[idx]['processed'] = stage_progress[idx]['total']
    finally:
        if render_thread:
            stop_render.set()
            render_thread.join()
            with render_lock:
                _render_stage_statuses()
            sys.stdout.flush()

    monitor.stats.files_skipped = stats.skipped_files


def compress_directory_legacy(directory_path: str, thorough_check: bool = False) -> LegacyCompressionStats:
    stats = LegacyCompressionStats()
    base_dir = Path(directory_path).resolve()

    print(f"\nChecking files in {directory_path} for proper compression branding...")
    if thorough_check:
        print("Using thorough checking mode - this will be slower but more accurate")

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