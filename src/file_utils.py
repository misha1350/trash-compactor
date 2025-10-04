import bisect
import logging
import ctypes
import subprocess
import os
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import wmi

from .config import MIN_COMPRESSIBLE_SIZE, SIZE_THRESHOLDS, SKIP_EXTENSIONS

_SIZE_BREAKS, _SIZE_LABELS = zip(*SIZE_THRESHOLDS)
KERNEL32 = ctypes.WinDLL('kernel32', use_last_error=True)


def get_size_category(file_size: int) -> str:
    index = bisect.bisect_right(_SIZE_BREAKS, file_size)
    return _SIZE_LABELS[index] if index < len(_SIZE_LABELS) else 'large'


def _hidden_startupinfo() -> subprocess.STARTUPINFO:
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def check_compression_with_compact(file_path: Path) -> bool:
    try:
        command = f'compact /a "{file_path}"'
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=_hidden_startupinfo(),
            shell=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return "0 are not" in result.stdout
    except Exception as exc:
        logging.error("Failed to check compression with compact: %s", exc)
        return False


def is_file_compressed(file_path: Path, thorough_check: bool = False) -> tuple[bool, int]:
    try:
        actual_size = file_path.stat().st_size
    except Exception as exc:
        logging.error("Failed to get actual file size: %s", exc)
        return False, 0

    getter = KERNEL32.GetCompressedFileSizeW
    getter.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    getter.restype = wintypes.DWORD

    high = wintypes.DWORD()
    low = getter(str(file_path), ctypes.byref(high))

    if low == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error:
            logging.error("Failed to get compressed size: %s", ctypes.WinError(error))
            return False, actual_size

    compressed_size = (high.value << 32) + low
    if compressed_size < actual_size:
        return True, compressed_size

    if thorough_check and compressed_size == actual_size:
        if check_compression_with_compact(file_path):
            logging.debug("File %s detected as compressed by compact command", file_path)
            return True, compressed_size

    return False, compressed_size


def should_compress_file(file_path: Path, thorough_check: bool = False) -> tuple[bool, str, int]:
    suffix = file_path.suffix.lower()
    if suffix in SKIP_EXTENSIONS:
        return False, f"Skipped due to extension {suffix}", 0

    try:
        file_size = file_path.stat().st_size
        if file_size < MIN_COMPRESSIBLE_SIZE:
            return False, f"File too small ({file_size} bytes)", file_size

        is_compressed, compressed_size = is_file_compressed(file_path, thorough_check)
        if is_compressed:
            return False, "File is already compressed", compressed_size

        return True, "File eligible for compression", file_size
    except Exception as exc:
        logging.error("Error checking file %s: %s", file_path, exc)
        return False, f"Error during check: {exc}", 0


def is_hard_drive(drive_path: str) -> bool:
    letter = _drive_letter(drive_path)
    if not letter:
        logging.debug("No drive letter found in %s", drive_path)
        return False

    try:
        inspector = _DriveInspector(letter)
        verdict = inspector.by_metadata()
        if verdict is not None:
            return verdict

        verdict = inspector.by_latency()
        if verdict is not None:
            return verdict

        inspector.note_alignment()
        logging.debug("Unable to definitively identify drive %s as HDD, assuming SSD/flash", letter)
        return False
    except Exception as exc:
        logging.error("Error detecting drive type: %s", exc)
        return False


def _drive_letter(drive_path: str) -> Optional[str]:
    if not drive_path:
        return None
    drive_letter = os.path.splitdrive(drive_path)[0]
    if drive_letter.endswith('\\'):
        drive_letter = drive_letter[:-1]
    return drive_letter or None


class _DriveInspector:
    def __init__(self, drive_letter: str):
        self.drive_letter = drive_letter
        self.conn = wmi.WMI()

    def by_metadata(self) -> Optional[bool]:
        for disk in self.conn.Win32_DiskDrive():
            logging.debug(
                "Inspecting disk: %s",
                {
                    'DeviceID': getattr(disk, 'DeviceID', 'N/A'),
                    'InterfaceType': getattr(disk, 'InterfaceType', 'N/A'),
                    'Description': getattr(disk, 'Description', 'N/A'),
                    'MediaType': getattr(disk, 'MediaType', 'N/A'),
                    'Model': getattr(disk, 'Model', 'N/A'),
                },
            )
            for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                for logical_disk in partition.associators("Win32_LogicalDiskToPartition"):
                    if logical_disk.DeviceID == self.drive_letter:
                        verdict = self._metadata_verdict(disk)
                        if verdict is not None:
                            return verdict
        return None

    def _metadata_verdict(self, disk) -> Optional[bool]:
        interface = getattr(disk, 'InterfaceType', '') or ''
        if 'nvme' in interface.lower():
            logging.debug("Drive %s is NVMe, treating as SSD", self.drive_letter)
            return False

        description = (getattr(disk, 'Description', '') or '').lower()
        if any(term in description for term in ['ssd', 'solid state', 'flash']):
            logging.debug("Drive %s describes itself as SSD/flash", self.drive_letter)
            return False
        if any(term in description for term in ['hard drive', 'hard disk']):
            logging.debug("Drive %s describes itself as HDD", self.drive_letter)
            return True

        media_type = (getattr(disk, 'MediaType', '') or '').lower()
        if any(term in media_type for term in ['ssd', 'solid', 'flash']):
            return False
        if any(term in media_type for term in ['hard', 'hdd', 'rotating']):
            return True

        model = (getattr(disk, 'Model', '') or '').lower()
        if any(term in model for term in ['ssd', 'nvme', 'solid state', 'm.2']):
            return False
        return None

    def by_latency(self) -> Optional[bool]:
        disk_number = self._physical_disk_number()
        if disk_number is None:
            return None

        for physical_disk in self.conn.Win32_PerfFormattedData_PerfDisk_PhysicalDisk():
            if physical_disk.Name == "_Total":
                continue
            try:
                disk_info = physical_disk.Name.split()
                if disk_info and int(disk_info[0]) == disk_number:
                    read_latency = getattr(physical_disk, 'AvgDiskSecPerRead', None)
                    write_latency = getattr(physical_disk, 'AvgDiskSecPerWrite', None)
                    logging.debug(
                        "Performance data for disk %s: read=%s, write=%s",
                        disk_number,
                        read_latency,
                        write_latency,
                    )
                    if read_latency and read_latency > 0.003:
                        logging.debug("Drive %s has HDD-like read latency: %ss", self.drive_letter, read_latency)
                        return True
                    if write_latency and write_latency > 0.003:
                        logging.debug("Drive %s has HDD-like write latency: %ss", self.drive_letter, write_latency)
                        return True
            except (ValueError, IndexError):
                logging.debug("Error processing physical disk performance data")
                continue
        return None

    def _physical_disk_number(self) -> Optional[int]:
        for relation in self.conn.Win32_LogicalDiskToPartition():
            try:
                if relation.Dependent.DeviceID == self.drive_letter:
                    antecedent = relation.Antecedent
                    disk_id = antecedent.split('PHYSICALDRIVE')[1]
                    number = int(''.join(filter(str.isdigit, disk_id)))
                    logging.debug("Found physical disk number %s for drive %s", number, self.drive_letter)
                    return number
            except (AttributeError, IndexError, ValueError):
                logging.debug("Failed to extract physical disk number from antecedent: %s", getattr(relation, 'Antecedent', 'N/A'))
        return None

    def note_alignment(self) -> None:
        for disk in self.conn.Win32_DiskDrive():
            for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                for logical_disk in partition.associators("Win32_LogicalDiskToPartition"):
                    if logical_disk.DeviceID == self.drive_letter:
                        # Alignment is a weak signal, yet logging it helps post-mortem drive reports
                        size = getattr(disk, 'Size', None)
                        block = getattr(disk, 'DefaultBlockSize', None)
                        logging.debug("Disk %s Size: %s, DefaultBlockSize: %s", getattr(disk, 'DeviceID', 'N/A'), size, block)
                        try:
                            if size and block and size % block == 0:
                                logging.debug("Drive %s has aligned sectors, common in HDDs", self.drive_letter)
                        except (TypeError, ZeroDivisionError):
                            logging.debug("Error calculating sector alignment for drive %s", self.drive_letter)
