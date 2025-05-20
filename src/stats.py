import logging
import sys
import time
import threading
import os
import re

class Spinner:
    """Simple spinner class for showing progress"""
    def __init__(self):
        self.spinner_chars = ['\\', '|', '/', '-']
        self.current_char = 0
        self.running = False
        self.spinner_thread = None
        self.message_prefix = " Compressing Files: "
        self.message_suffix = ""
        self.last_line_length = 0
        
    def format_path(self, full_path, base_dir):
        """Format file path to show a condensed relative path"""
        # Convert to relative path
        try:
            rel_path = os.path.relpath(full_path, base_dir)
            
            # Split path into parts
            parts = rel_path.split(os.sep)
            
            # Handle different depths
            if len(parts) <= 2:
                # Near the surface, show full relative path
                return "/".join(parts)
            else:
                # Deep path, show first folder, ellipses for middle folders, and filename
                middle_dots = "/..." * min(3, len(parts) - 2)  # Up to 3 sets of ".../..."
                return f"{parts[0]}{middle_dots}{parts[-1]}"
                
        except Exception:
            # Fallback if path handling fails
            return os.path.basename(full_path)
    
    def spin(self):
        """Update the spinner character"""
        while self.running:
            # Clear the entire line with spaces and reset cursor to start of line
            sys.stdout.write(f"\r{' ' * self.last_line_length}\r")
            
            # Write the updated spinner with the spinner character before the path
            output = f"{self.message_prefix}{self.spinner_chars[self.current_char]} {self.message_suffix}"
            sys.stdout.write(output)
            sys.stdout.flush()
            
            # Store line length for future clearing
            self.last_line_length = len(output)
            
            self.current_char = (self.current_char + 1) % len(self.spinner_chars)
            time.sleep(0.1)
    
    def start(self, message_prefix=None, message_suffix=None):
        """Start the spinner"""
        if message_prefix:
            self.message_prefix = message_prefix
        if message_suffix is not None:  # Allow empty string
            self.message_suffix = message_suffix
        
        self.running = True
        sys.stdout.write("\r")
        self.spinner_thread = threading.Thread(target=self.spin)
        self.spinner_thread.daemon = True
        self.spinner_thread.start()
    
    def stop(self):
        """Stop the spinner"""
        self.running = False
        if self.spinner_thread:
            self.spinner_thread.join()
        # Clear the entire line with spaces
        sys.stdout.write(f"\r{' ' * self.last_line_length}\r")
        sys.stdout.flush()


class CompressionStats:
    def __init__(self):
        self.compressed_files = 0
        self.skipped_files = 0
        self.already_compressed_files = 0  # New counter for already compressed files
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.errors = []
        self.total_skipped_size = 0


class LegacyCompressionStats:
    """Stats for legacy compression branding mode"""
    def __init__(self):
        self.total_files = 0
        self.branded_files = 0
        self.still_unmarked = 0
        self.errors = []


def print_compression_summary(stats: CompressionStats):
    """Print compression statistics"""
    logging.info("\nCompression Summary")
    logging.info("------------------")
    logging.info(f"Files compressed: {stats.compressed_files}")
    logging.info(f"Files skipped: {stats.skipped_files} (of these, {stats.already_compressed_files} are already compressed)")
    
    if stats.compressed_files == 0:
        logging.info("\nThis directory may have already been compressed.")
        return
    
    # Calculate total original size including skipped files
    
    total_original = stats.total_original_size
    total_compressed = stats.total_compressed_size
    
    logging.info(f"\nOriginal size: {total_original / (1024 * 1024):.2f} MB")
    
    if total_original > 0:
        space_saved = total_original - total_compressed
        logging.info(f"Space saved: {space_saved / (1024 * 1024):.2f} MB")
        
        ratio = (space_saved / total_original) * 100
        logging.info(f"Overall compression ratio: {ratio:.2f}%")
        logging.info(f"Size after compression: {total_compressed / (1024 * 1024):.2f} MB")
    
    if stats.errors:
        logging.info("\nErrors encountered:")
        for error in stats.errors:
            logging.error(error)