import logging

class CompressionStats:
    def __init__(self):
        self.compressed_files = 0
        self.skipped_files = 0
        self.already_compressed_files = 0  # New counter for already compressed files
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.errors = []
        self.total_skipped_size = 0

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
    
    # TODO: Logging strings were changed, but the variable names are wrong
    # instead of fixing the core logic, the variable names should be changed
    total_original = stats.total_original_size
    total_compressed = stats.total_compressed_size
    
    logging.info(f"\nOriginal size: {total_original / (1024 * 1024):.2f} MB")
    logging.info(f"Space saved: {total_compressed / (1024 * 1024):.2f} MB")
    
    if total_original > 0:
        ratio = (1 - total_compressed / total_original) * 100
        saved = total_original - total_compressed
        logging.info(f"Overall compression ratio: {ratio:.2f}%")
        logging.info(f"Size after compression: {saved / (1024 * 1024):.2f} MB")
    
    if stats.errors:
        logging.info("\nErrors encountered:")
        for error in stats.errors:
            logging.error(error)