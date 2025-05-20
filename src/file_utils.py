import bisect
import logging
import ctypes
import subprocess
import os
import wmi
from ctypes import wintypes
from pathlib import Path
from .config import SKIP_EXTENSIONS, SIZE_THRESHOLDS, MIN_COMPRESSIBLE_SIZE

def get_size_category(file_size: int) -> str:
    """Determine size category of file using binary search"""
    sizes, categories = zip(*SIZE_THRESHOLDS)
    index = bisect.bisect_right(sizes, file_size)
    return categories[index] if index < len(categories) else 'large'

"""
Rant time:
I've tried everything to get this function to work all the time, but:
some files simply cannot be checked for compression status.
Not with the GetCompressedFileSizeW function, not with the "compact /a" command.
I've spent an entire evening and millions of tokens on this, but it appears that the only way
would be to simply call "compact /c" on everything, if you intend to run this on a crontab every single day
and reliably skipping compressed files all the time.
Instead of designing a file system that can contain metadata for each file, like file permissions in Linux,
Microsoft decided to make reinvent the wheel, and new ways to force you to buy a larger SSD.
"""

def check_compression_with_compact(file_path: Path) -> bool:
    """Check if a file is compressed using compact command"""
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = f'compact /a "{str(file_path)}"'
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            shell=True,
            text=True
        )
        
        # If command execution failed, fall back to size comparison
        if result.returncode != 0:
            return False
        
        # Check for a specific substring in the output to determine compression status
        return "0 are not" in result.stdout
        
    except Exception as e:
        logging.error(f"Failed to check compression with compact: {e}")
        return False

def is_file_compressed(file_path: Path, thorough_check: bool = False) -> tuple[bool, int]:
    """
    Check if a file is compressed and return its compressed size
    
    Args:
        file_path: Path to the file to check
        thorough_check: Whether to perform additional thorough checks (slower but more accurate)
    """
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    
    # Get actual file size
    try:
        actual_size = file_path.stat().st_size
    except Exception as e:
        logging.error(f"Failed to get actual file size: {e}")
        return False, 0

    # Get compressed size
    GetCompressedFileSizeW = kernel32.GetCompressedFileSizeW
    GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    GetCompressedFileSizeW.restype = wintypes.DWORD

    high_order = wintypes.DWORD()
    low_order = GetCompressedFileSizeW(str(file_path), ctypes.byref(high_order))
    
    if low_order == 0xFFFFFFFF:
        error = ctypes.get_last_error()
        if error != 0:
            logging.error(f"Failed to get compressed size: {ctypes.WinError(error)}")
            return False, actual_size
    
    compressed_size = (high_order.value << 32) + low_order
    
    # Primary check: compressed size less than actual size
    is_compressed_by_size = compressed_size < actual_size
    
    # If file is already deemed compressed by size check, no need for fallback
    if is_compressed_by_size:
        return True, compressed_size
        
    # Secondary check: Only use compact command when thorough_check is enabled
    if thorough_check and compressed_size == actual_size:
        is_compressed_by_attr = check_compression_with_compact(file_path)
        if is_compressed_by_attr:
            logging.debug(f"File {file_path} detected as compressed by compact command")
            return True, compressed_size
            
    return False, compressed_size

def should_compress_file(file_path: Path, thorough_check: bool = False) -> tuple[bool, str, int]:
    """
    Check if file is eligible for compression and return its compressed size
    
    Args:
        file_path: Path to the file to check
        thorough_check: Whether to perform additional thorough checks (slower but more accurate)
    """
    if file_path.suffix.lower() in SKIP_EXTENSIONS:
        return False, f"Skipped due to extension {file_path.suffix}", 0

    try:
        file_size = file_path.stat().st_size
        if file_size < MIN_COMPRESSIBLE_SIZE:
            return False, f"File too small ({file_size} bytes)", file_size

        is_compressed, compressed_size = is_file_compressed(file_path, thorough_check)
        if is_compressed:
            return False, "File is already compressed", compressed_size

        return True, "File eligible for compression", file_size

    except Exception as e:
        logging.error(f"Error checking file {file_path}: {str(e)}")
        return False, f"Error during check: {str(e)}", 0

def is_hard_drive(drive_path: str) -> bool:
    """
    Check if the specified drive is a traditional spinning hard disk (HDD).
    
    Args:
        drive_path: Path to check (e.g., 'C:\\', 'D:\\Users\\...')
    
    Returns:
        bool: True if the drive is a spinning hard disk, False otherwise (SSD, eMMC, etc.)
    """
    try:
        # Extract drive letter from the path
        if not drive_path:
            logging.debug("Empty drive_path provided")
            return False
            
        drive_letter = os.path.splitdrive(drive_path)[0]
        if not drive_letter:
            logging.debug("No drive letter found in the path")
            return False
            
        # Ensure drive letter format is correct (e.g., 'C:')
        if drive_letter.endswith('\\'):
            drive_letter = drive_letter[:-1]
        
        c = wmi.WMI()
        
        # Method 1: Check interface type and direct properties
        for disk in c.Win32_DiskDrive():
            debug_info = {
                'DeviceID': getattr(disk, 'DeviceID', 'N/A'),
                'InterfaceType': getattr(disk, 'InterfaceType', 'N/A'),
                'Description': getattr(disk, 'Description', 'N/A'),
                'MediaType': getattr(disk, 'MediaType', 'N/A'),
                'Model': getattr(disk, 'Model', 'N/A')
            }
            logging.debug(f"Inspecting disk: {debug_info}")
            for partition in disk.associators("Win32_DiskDriveToDiskPartition"):
                for logical_disk in partition.associators("Win32_LogicalDiskToPartition"):
                    if logical_disk.DeviceID == drive_letter:
                        # Interface type check (NVMe is always SSD)
                        if hasattr(disk, 'InterfaceType') and disk.InterfaceType:
                            logging.debug(f"Disk {disk.DeviceID} InterfaceType: {disk.InterfaceType}")
                            if 'nvme' in disk.InterfaceType.lower():
                                logging.debug(f"Drive {drive_letter} is NVMe, definitely not an HDD")
                                return False
                        
                        # Check descriptor fields
                        if hasattr(disk, 'Description') and disk.Description:
                            desc = disk.Description.lower()
                            logging.debug(f"Disk {disk.DeviceID} Description: {desc}")
                            if any(term in desc for term in ['ssd', 'solid state', 'flash']):
                                logging.debug(f"Drive {drive_letter} describes itself as SSD/flash")
                                return False
                            if 'hard drive' in desc or 'hard disk' in desc:
                                logging.debug(f"Drive {drive_letter} describes itself as HDD")
                                return True
                        
                        # Media type check
                        if hasattr(disk, 'MediaType') and disk.MediaType:
                            media = disk.MediaType.lower()
                            logging.debug(f"Disk {disk.DeviceID} MediaType: {media}")
                            if 'ssd' in media or 'solid' in media or 'flash' in media:
                                return False
                            if 'hard' in media or 'hdd' in media or 'rotating' in media:
                                return True
                                
                        # Model checks - lowest priority
                        if hasattr(disk, 'Model'):
                            model = disk.Model.lower()
                            logging.debug(f"Disk {disk.DeviceID} Model: {model}")
                            # Clear SSD indicators
                            if any(term in model for term in ['ssd', 'nvme', 'solid state', 'm.2']):
                                return False
        
        # Method 2: Performance characteristics - the most reliable indicator
        # HDDs have distinct performance profiles (high latency, long seek times)
        disk_to_check = None
        
        # First get the physical disk number for our drive letter
        for partition in c.Win32_LogicalDiskToPartition():
            if partition.Dependent.DeviceID == drive_letter:
                # Extract disk number from partition path
                # Format is typically like: "\\.\PHYSICALDRIVE1"
                try:
                    antecedent = partition.Antecedent
                    disk_num = int(''.join(filter(str.isdigit, antecedent.split('PHYSICALDRIVE')[1])))
                    disk_to_check = disk_num
                    logging.debug(f"Found physical disk number {disk_num} for drive {drive_letter}")
                    break
                except (IndexError, ValueError):
                    logging.debug(f"Failed to extract physical disk number from antecedent: {partition.Antecedent}")
                    pass
        
        if disk_to_check is not None:
            # Check disk performance counters
            for physical_disk in c.Win32_PerfFormattedData_PerfDisk_PhysicalDisk():
                # Skip _Total
                if physical_disk.Name == "_Total":
                    continue
                
                try:
                    # Try to match disk number
                    disk_info = physical_disk.Name.split()
                    if len(disk_info) > 0 and int(disk_info[0]) == disk_to_check:
                        logging.debug(f"Performance data for disk {disk_to_check}: Read={getattr(physical_disk, 'AvgDiskSecPerRead', 'N/A')}, Write={getattr(physical_disk, 'AvgDiskSecPerWrite', 'N/A')}")
                        # HDDs have much higher seek times (typically >4ms)
                        # SSDs and flash storage are much faster (<1ms)
                        if hasattr(physical_disk, 'AvgDiskSecPerRead'):
                            if physical_disk.AvgDiskSecPerRead > 0.003:  # >3ms read time suggests HDD
                                logging.debug(f"Drive {drive_letter} has HDD-like read latency: {physical_disk.AvgDiskSecPerRead}s")
                                return True
                        
                        if hasattr(physical_disk, 'AvgDiskSecPerWrite'):
                            if physical_disk.AvgDiskSecPerWrite > 0.003:  # >3ms write time suggests HDD
                                logging.debug(f"Drive {drive_letter} has HDD-like write latency: {physical_disk.AvgDiskSecPerWrite}s")
                                return True
                except (ValueError, IndexError):
                    logging.debug("Error processing physical disk performance data")
                    continue
        
        # Method 3: PHYSICALDISK format check
        # Try direct disk property access using device instance ID
        for disk_drive in c.Win32_DiskDrive():
            for partition in disk_drive.associators("Win32_DiskDriveToDiskPartition"):
                for logical_disk in partition.associators("Win32_LogicalDiskToPartition"):
                    if logical_disk.DeviceID == drive_letter:
                        if hasattr(disk_drive, 'Size') and hasattr(disk_drive, 'DefaultBlockSize'):
                            try:
                                logging.debug(f"Disk {disk_drive.DeviceID} Size: {disk_drive.Size}, DefaultBlockSize: {disk_drive.DefaultBlockSize}")
                                # Calculate number of physical sectors
                                # HDDs typically have physical sectors and logical sectors that match
                                # Many SSDs have mismatching physical/logical sectors for wear leveling
                                if disk_drive.Size % disk_drive.DefaultBlockSize == 0:
                                    logging.debug(f"Drive {drive_letter} has aligned sectors, common in HDDs")
                                    # Not definitive, just additional evidence
                            except (TypeError, ZeroDivisionError):
                                logging.debug("Error calculating sector alignment")
                                pass
        
        logging.debug(f"Unable to definitively identify drive {drive_letter} as HDD, assuming SSD/flash")
        return False
        
    except Exception as e:
        logging.error(f"Error detecting drive type: {str(e)}")
        # In case of error, be conservative and don't flag as HDD
        return False
