"""Console output that survives a console encoding without the characters we print."""

from __future__ import annotations

import sys


def tolerate_console_encoding() -> None:
    """Print '?' for characters the console cannot encode instead of crashing.

    A cp1252 Windows console cannot encode the check marks and arrows the
    commands print, and the UnicodeEncodeError would end the command.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
