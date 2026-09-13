import logging
import re
from typing import Any

class PIIMaskingFormatter(logging.Formatter):
    """
    Masks PII like emails in log messages for security and compliance.
    """
    # Simple email regex for masking
    EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')

    def format(self, record: logging.LogRecord) -> str:
        original_msg = super().format(record)
        return self.EMAIL_PATTERN.sub("[MASKED_EMAIL]", original_msg)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Console Handler with PII masking
    handler = logging.StreamHandler()
    formatter = PIIMaskingFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    
    # Reset existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
        
    logger.addHandler(handler)
    return logger

# Initialize on import
logger = setup_logging()
