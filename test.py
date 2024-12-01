import logging
from pathlib import Path
from src.file_utils import is_file_compressed

def test_compression_status(file_path_str):
    file_path = Path(file_path_str)
    try:
        compressed = is_file_compressed(file_path)
        status = "Compressed" if compressed else "Not Compressed"
        print(f"File: {file_path}")
        print(f"Compression Status: {status}")
    except Exception as e:
        print(f"Error checking compression status for {file_path}: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    # Replace with paths to test files
    test_files = [
        r"C:\Users\mewhenthe\Downloads\Telegram Desktop\Отчет о проделанной работе (5).docx",
        r"C:\Users\mewhenthe\Downloads\Telegram Desktop\Отчет о проделанной работе (6).docx",
        r"C:\Users\mewhenthe\Downloads\Telegram Desktop\Отчет о проделанной работе.docx",
        r"C:\Users\mewhenthe\Downloads\Telegram Desktop\Отчет по курсу VK Образование (2).docx",
    ]
    
    for file in test_files:
        test_compression_status(file)