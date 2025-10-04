import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional


class Spinner:
    def __init__(self) -> None:
        self._chars = ['\\', '|', '/', '-']
        self._index = 0
        self._running = False
        self._thread = None
        self._message = ""
        self._last_line_length = 0
        self._lock = threading.Lock()
        self.processed = 0
        self.total = 0

    def format_path(self, full_path: str, base_dir: str) -> str:
        try:
            rel_path = os.path.relpath(full_path, base_dir)
        except Exception:
            rel_path = os.path.basename(full_path)

        parts = rel_path.split(os.sep)
        if len(parts) <= 2:
            return "/".join(parts)

        # A single ellipsis keeps the spinner readable even for deeply nested files
        head, tail = parts[0], parts[-1]
        middle = '...'
        return f"{head}/{middle}/{tail}"

    def _spin(self) -> None:
        while self._running:
            with self._lock:
                progress = f"({self.processed}/{self.total})" if self.total else ""
                output = f"\r Compressing Files {progress}: {self._chars[self._index]} {self._message}"
                output = output.ljust(self._last_line_length)
                sys.stdout.write(output)
                sys.stdout.flush()
                self._last_line_length = len(output)
                self._index = (self._index + 1) % len(self._chars)
            time.sleep(0.2)

    def start(self, total: int = 0) -> None:
        self.total = total
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def update(self, processed: int, current_file: Optional[str] = None) -> None:
        with self._lock:
            self.processed = processed
            if current_file:
                self._message = current_file

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        sys.stdout.write(f"\r{' ' * self._last_line_length}\r")
        sys.stdout.flush()


@dataclass
class CompressionStats:
    compressed_files: int = 0
    skipped_files: int = 0
    already_compressed_files: int = 0
    total_original_size: int = 0
    total_compressed_size: int = 0
    total_skipped_size: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class LegacyCompressionStats:
    total_files: int = 0
    branded_files: int = 0
    still_unmarked: int = 0
    errors: List[str] = field(default_factory=list)


def print_compression_summary(stats: CompressionStats) -> None:
    logging.info("\nCompression Summary")
    logging.info("------------------")
    logging.info("Files compressed: %s", stats.compressed_files)
    logging.info(
        "Files skipped: %s (of these, %s are already compressed)",
        stats.skipped_files,
        stats.already_compressed_files,
    )

    if stats.compressed_files == 0:
        logging.info("\nThis directory may have already been compressed.")
        return

    total_original = stats.total_original_size
    total_compressed = stats.total_compressed_size
    logging.info("\nOriginal size: %.2f MB", total_original / (1024 * 1024))

    if total_original > 0:
        space_saved = total_original - total_compressed
        logging.info("Space saved: %.2f MB", space_saved / (1024 * 1024))
        ratio = (space_saved / total_original) * 100
        logging.info("Overall compression ratio: %.2f%%", ratio)
        logging.info("Size after compression: %.2f MB", total_compressed / (1024 * 1024))

    if stats.errors:
        logging.info("\nErrors encountered:")
        for error in stats.errors:
            logging.error(error)