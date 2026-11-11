"""Central logging configuration for the app (simple)."""
import logging


def configure_logging(level=logging.INFO):
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt)
    # reduce verbosity for some libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
