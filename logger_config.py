import logging
import os
import sys
from datetime import datetime

# Define custom log levels (if needed) or just use standard ones
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

import re

existing_run_numbers = []

for filename in os.listdir(LOG_DIR):
    match = re.match(r"^(\d+)\.log$", filename)
    if match:
        existing_run_numbers.append(int(match.group(1)))

run_number = (max(existing_run_numbers) + 1) if existing_run_numbers else 1
LOG_FILE = os.path.join(LOG_DIR, f"{run_number}.log")

# Create a custom formatter for the console
class ConsoleFormatter(logging.Formatter):
    """Format logs for the console (INFO and above) without timestamps."""
    def format(self, record):
        # We don't add timestamps for console output, keeping it clean like a CLI
        if record.levelno == logging.INFO:
            return record.getMessage()
        elif record.levelno == logging.WARNING:
            return f"[!] WARNING: {record.getMessage()}"
        elif record.levelno == logging.ERROR:
            return f"[-] ERROR: {record.getMessage()}"
        elif record.levelno == logging.CRITICAL:
            return f"[-] FATAL: {record.getMessage()}"
        return record.getMessage()

# Create a custom formatter for the file
class FileFormatter(logging.Formatter):
    """Format logs for the file with full timestamps and levels."""
    def format(self, record):
        fmt = "%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

def setup_logger():
    logger = logging.getLogger("MAHABOCW")
    
    # Avoid adding handlers multiple times if imported multiple times
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Prevent propagating to PaddleOCR's root logger

    # 1. Console Handler (INFO+)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    # Ensure stdout is output safely to avoid emoji/unicode encoding errors
    # (Though we won't use emojis, we configure the handler)
    logger.addHandler(console_handler)

    # 2. File Handler (DEBUG+)
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(FileFormatter())
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()
