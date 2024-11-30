import logging

class CompressionStats:
    def __init__(self):
        self.compressed_files = 0
        self.skipped_files = 0
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.errors = []

def print_compression_summary(stats: CompressionStats):
    """Print compression statistics"""
    logging.info("\nCompression Summary:")
    logging.info(f"Files compressed: {stats.compressed_files}")
    logging.info(f"Files skipped: {stats.skipped_files}")
    
    if stats.total_original_size > 0:
        ratio = (1 - stats.total_compressed_size / stats.total_original_size) * 100
        saved = stats.total_original_size - stats.total_compressed_size
        logging.info(f"Overall compression ratio: {ratio:.2f}%")
        logging.info(f"Space saved: {saved / 1024 / 1024:.2f} MB")
    
    if stats.errors:
        logging.info("\nErrors encountered:")
        for error in stats.errors:
            logging.error(error)