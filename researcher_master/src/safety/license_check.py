"""Minimal license/rights checker placeholder.

This is a conservative stub: it currently accepts URLs but logs a warning.
In production this should integrate with a proper license detection service
or a metadata database.
"""
import logging

logger = logging.getLogger(__name__)


def check_license(url: str) -> bool:
    # Very conservative placeholder: accept but log a warning for manual review
    logger.warning(f"License check for {url} is permissive by default (stub).")
    return True
