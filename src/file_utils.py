import bisect
import ctypes
import logging
import os
import subprocess
from dataclasses import dataclass
from ctypes import wintypes
from pathlib import Path
from typing import Optional

import wmi

from .config import DEFAULT_EXCLUDE_DIRECTORIES, MIN_COMPRESSIBLE_SIZE, SIZE_THRESHOLDS, SKIP_EXTENSIONS


def _normalize_for_compare(path: str | Path) -> str:
    normalized = os.path.normcase(os.path.normpath(str(path)))
    if len(normalized) == 2 and normalized[1] == ':':
        return normalized + os.sep
    return normalized


_DEFAULT_EXCLUDE_MAP: dict[str, str] = {
    _normalize_for_compare(candidate): os.path.normpath(candidate)
    for candidate in DEFAULT_EXCLUDE_DIRECTORIES
}


def _match_exclusion(normalized: str) -> tuple[bool, Optional[str]]:
    for excluded_norm, display in _DEFAULT_EXCLUDE_MAP.items():
        if normalized == excluded_norm:
            return True, f"Protected system directory ({display})"
        prefix = excluded_norm + os.sep
        if normalized.startswith(prefix):
            return True, f"Within protected system directory ({display})"
    return False, None


_SIZE_BREAKS, _SIZE_LABELS = zip(*SIZE_THRESHOLDS)
KERNEL32 = ctypes.WinDLL('kernel32', use_last_error=True)

DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_CDROM = 5
DRIVE_RAMDISK = 6

IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
PROPERTY_STANDARD_QUERY = 0
STORAGE_DEVICE_SEEK_PENALTY_PROPERTY = 7

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [
        ('PropertyId', ctypes.c_int),
        ('QueryType', ctypes.c_int),
        ('AdditionalParameters', ctypes.c_byte * 1),
    ]


class DEVICE_SEEK_PENALTY_DESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ('Version', wintypes.DWORD),
        ('Size', wintypes.DWORD),
        ('IncursSeekPenalty', wintypes.BOOLEAN),
    ]


KERNEL32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
KERNEL32.GetDriveTypeW.restype = wintypes.UINT

KERNEL32.GetVolumeInformationW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    wintypes.DWORD,
]
KERNEL32.GetVolumeInformationW.restype = wintypes.BOOL

KERNEL32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
KERNEL32.CreateFileW.restype = wintypes.HANDLE

KERNEL32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
KERNEL32.DeviceIoControl.restype = wintypes.BOOL

KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL32.CloseHandle.restype = wintypes.BOOL


@dataclass(frozen=True)
class VolumeDetails:
    anchor: Optional[str]
    drive_letter: Optional[str]
    drive_type: int
    filesystem: Optional[str]
    rotational: Optional[bool]


def _volume_anchor(path: str) -> Optional[str]:
    if not path:
        return None
    drive, _ = os.path.splitdrive(path)
    if not drive:
        return None
    drive = drive.rstrip('\\')
    if not drive:
        return None
    return f"{drive}\\"


def _filesystem_name(anchor: str) -> Optional[str]:
    volume_name = ctypes.create_unicode_buffer(256)
    fs_name = ctypes.create_unicode_buffer(256)
    serial = wintypes.DWORD()
    max_component = wintypes.DWORD()
    flags = wintypes.DWORD()
    if not KERNEL32.GetVolumeInformationW(
        anchor,
        volume_name,
        len(volume_name),
        ctypes.byref(serial),
        ctypes.byref(max_component),
        ctypes.byref(flags),
        fs_name,
        len(fs_name),
    ):
        error = ctypes.get_last_error()
        if error:
            logging.debug("GetVolumeInformationW failed for %s: %s", anchor, ctypes.WinError(error))
        return None
    name = fs_name.value.strip()
    return name.upper() if name else None


def _open_physical_drive(number: int) -> Optional[wintypes.HANDLE]:
    device_path = f"\\\\.\\PhysicalDrive{number}"
    handle = KERNEL32.CreateFileW(
        device_path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        if error:
            logging.debug("CreateFileW failed for %s: %s", device_path, ctypes.WinError(error))
        return None
    return handle


def get_volume_details(path: str) -> VolumeDetails:
    anchor = _volume_anchor(path)
    letter = _drive_letter(path)
    if not anchor:
        logging.debug("Unable to resolve volume anchor for %s", path)
        return VolumeDetails(None, letter, DRIVE_UNKNOWN, None, None)

    drive_type = KERNEL32.GetDriveTypeW(anchor)
    filesystem = None
    if drive_type not in {DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR}:
        filesystem = _filesystem_name(anchor)

    rotational = None
    if drive_type == DRIVE_FIXED and letter and len(letter) == 2 and letter[1] == ':':
        inspector = _DriveInspector(letter)
        rotational = inspector.seek_penalty()
        if rotational is None:
            rotational = inspector.by_metadata()
            if rotational is None:
                rotational = inspector.by_latency()
                if rotational is None:
                    inspector.note_alignment()

    return VolumeDetails(anchor, letter, drive_type, filesystem, rotational)


def get_size_category(file_size: int) -> str:
    index = bisect.bisect_right(_SIZE_BREAKS, file_size)
    return _SIZE_LABELS[index] if index < len(_SIZE_LABELS) else 'large'


def should_skip_directory(directory: Path) -> tuple[bool, str]:
    normalized = _normalize_for_compare(directory)
    match, reason = _match_exclusion(normalized)
    if match:
        return True, reason or ""
    return False, ""


def is_protected_path(path: str | Path) -> bool:
    normalized = _normalize_for_compare(path)
    match, _ = _match_exclusion(normalized)
    return match


def get_protection_reason(path: str | Path) -> Optional[str]:
    normalized = _normalize_for_compare(path)
    _, reason = _match_exclusion(normalized)
    return reason


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
    try:
        details = get_volume_details(drive_path)
    except Exception as exc:
        logging.error("Error detecting drive type: %s", exc)
        return False

    if details.drive_type != DRIVE_FIXED:
        logging.debug(
            "Volume %s reports drive type %s; treating as non-HDD",
            details.drive_letter or drive_path,
            details.drive_type,
        )
        return False

    if details.rotational is True:
        return True

    if details.rotational is False:
        return False

    logging.debug(
        "Unable to definitively identify drive %s as HDD, assuming SSD/flash",
        details.drive_letter or drive_path,
    )
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
        self._disk_number: Optional[int] = None

    def seek_penalty(self) -> Optional[bool]:
        disk_number = self._physical_disk_number()
        if disk_number is None:
            return None

        handle = _open_physical_drive(disk_number)
        if handle is None:
            return None

        try:
            query = STORAGE_PROPERTY_QUERY()
            query.PropertyId = STORAGE_DEVICE_SEEK_PENALTY_PROPERTY
            query.QueryType = PROPERTY_STANDARD_QUERY

            descriptor = DEVICE_SEEK_PENALTY_DESCRIPTOR()
            returned = wintypes.DWORD()
            # Some controllers (notably eMMC and SD bridges) decline this IOCTL, so it might fall back to softer signals
            success = KERNEL32.DeviceIoControl(
                handle,
                IOCTL_STORAGE_QUERY_PROPERTY,
                ctypes.byref(query),
                ctypes.sizeof(query),
                ctypes.byref(descriptor),
                ctypes.sizeof(descriptor),
                ctypes.byref(returned),
                None,
            )
            if not success:
                error = ctypes.get_last_error()
                if error:
                    logging.debug(
                        "DeviceIoControl(query seek penalty) failed for %s: %s",
                        self.drive_letter,
                        ctypes.WinError(error),
                    )
                return None
            return bool(descriptor.IncursSeekPenalty)
        finally:
            KERNEL32.CloseHandle(handle)

    def by_metadata(self) -> Optional[bool]:
        disk_number = self._physical_disk_number()
        if disk_number is None:
            return None

        device_id = f"\\\\.\\PHYSICALDRIVE{disk_number}"
        disks = self.conn.Win32_DiskDrive(DeviceID=device_id)
        for disk in disks:
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
        if self._disk_number is not None:
            return self._disk_number

        for relation in self.conn.Win32_LogicalDiskToPartition():
            try:
                if relation.Dependent.DeviceID == self.drive_letter:
                    antecedent = relation.Antecedent
                    disk_id = antecedent.split('PHYSICALDRIVE')[1]
                    number = int(''.join(filter(str.isdigit, disk_id)))
                    logging.debug("Found physical disk number %s for drive %s", number, self.drive_letter)
                    self._disk_number = number
                    return number
            except (AttributeError, IndexError, ValueError):
                logging.debug(
                    "Failed to extract physical disk number from antecedent: %s",
                    getattr(relation, 'Antecedent', 'N/A'),
                )
        return None

    def note_alignment(self) -> None:
        disk_number = self._physical_disk_number()
        if disk_number is None:
            return

        device_id = f"\\\\.\\PHYSICALDRIVE{disk_number}"
        disks = self.conn.Win32_DiskDrive(DeviceID=device_id)
        for disk in disks:
            # Alignment is a weak signal, yet logging it helps post-mortem drive reports
            size = getattr(disk, 'Size', None)
            block = getattr(disk, 'DefaultBlockSize', None)
            logging.debug("Disk %s Size: %s, DefaultBlockSize: %s", getattr(disk, 'DeviceID', 'N/A'), size, block)
            try:
                if size and block and size % block == 0:
                    logging.debug("Drive %s has aligned sectors, common in HDDs", self.drive_letter)
            except (TypeError, ZeroDivisionError):
                logging.debug("Error calculating sector alignment for drive %s", self.drive_letter)
