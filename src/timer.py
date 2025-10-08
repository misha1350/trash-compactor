import logging
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class TimingStats:
    total_time: float = 0.0
    file_scan_time: float = 0.0
    compression_time: float = 0.0
    total_files: int = 0
    files_compressed: int = 0
    files_skipped: int = 0


    @property
    def avg_time_per_file(self) -> float:
        return self.total_time / self.total_files if self.total_files else 0.0

    @property
    def avg_compression_time(self) -> float:
        return self.compression_time / self.files_compressed if self.files_compressed else 0.0

    @property
    def scan_throughput(self) -> float:
        return self.total_files / self.file_scan_time if self.file_scan_time else 0.0

    @property
    def work_throughput(self) -> float:
        return self.files_compressed / self.work_duration if self.work_duration else 0.0

    @property
    def work_duration(self) -> float:
        return self.total_time - self.file_scan_time if self.total_time > self.file_scan_time else 0.0

    def print_summary(self) -> None:
        logging.info("")
        logging.info("Performance summary")
        logging.info("  elapsed total : %.3fs", self.total_time)
        logging.info("  scan duration : %.3fs (%s)", self.file_scan_time, self._percent(self.file_scan_time))
        logging.info("  work duration : %.3fs (%s)", self.work_duration, self._percent(self.work_duration))
        logging.info("  files handled : %d", self.total_files)
        logging.info("    compressed  : %d", self.files_compressed)
        logging.info("    skipped     : %d", self.files_skipped)
        logging.info("  avg per file  : %.4fs", self.avg_time_per_file)
        if self.files_compressed:
            logging.info("  avg compress  : %.4fs", self.avg_compression_time)
        logging.info("  scan throughput    : %.2f files/s", self.scan_throughput)
        logging.info("  work throughput    : %.2f files/s", self.work_throughput)

    def _percent(self, span: float) -> str:
        return f"{(span / self.total_time) * 100:.1f}%" if self.total_time else "0.0%"


class Timer:
    def __init__(self, name: str = "operation", log_on_exit: bool = False) -> None:
        self.name = name
        self.log_on_exit = log_on_exit
        self.start_time: Optional[float] = None
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.start_time is None:
            return False
        self.elapsed = time.perf_counter() - self.start_time
        if self.log_on_exit:
            logging.debug("%s took %.3fs", self.name, self.elapsed)
        return False

    def get_elapsed(self) -> float:
        return time.perf_counter() - self.start_time if self.start_time is not None else 0.0


class PerformanceMonitor:
    def __init__(self) -> None:
        self.stats = TimingStats()
        self._operation_start: Optional[float] = None

    def start_operation(self) -> None:
        self._operation_start = time.perf_counter()

    def end_operation(self) -> None:
        if self._operation_start is not None:
            self.stats.total_time = time.perf_counter() - self._operation_start

    def time_file_scan(self) -> "SectionTimer":
        return SectionTimer(self, 'file_scan_time')

    def time_compression(self) -> "SectionTimer":
        return SectionTimer(self, 'compression_time')

    def increment_file_count(self) -> None:
        self.stats.total_files += 1

    def increment_compressed_count(self) -> None:
        self.stats.files_compressed += 1

    def increment_skipped_count(self) -> None:
        self.stats.files_skipped += 1

    def get_stats(self) -> TimingStats:
        return self.stats

    def print_summary(self) -> None:
        self.stats.print_summary()


class SectionTimer:
    def __init__(self, monitor: PerformanceMonitor, stat_name: str) -> None:
        self.monitor = monitor
        self.stat_name = stat_name
        self.start_time: Optional[float] = None

    def __enter__(self) -> "SectionTimer":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.start_time is None:
            return False
        elapsed = time.perf_counter() - self.start_time
        current_value = getattr(self.monitor.stats, self.stat_name)
        setattr(self.monitor.stats, self.stat_name, current_value + elapsed)
        return False
