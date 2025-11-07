import logging
from pathlib import Path

logger = logging.getLogger("chatstack")
if not logger.handlers:
    # Console handler
    h = logging.StreamHandler()
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    h.setFormatter(fmt)
    logger.addHandler(h)

    # File handler (best-effort; ignore failures)
    try:
        log_path = Path.cwd() / "chatstack.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass

logger.setLevel(logging.INFO)
