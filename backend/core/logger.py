import logging
import sys

# Not using logging.basicConfig(level=logging.DEBUG) 
# basicConfig is a global configuration. 
# It affects every logger in the entire application including 
# third party libraries like SQLAlchemy, LangChain, uvicorn
# terminal is flooded with logs from irrelevant libraries.

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    return logger