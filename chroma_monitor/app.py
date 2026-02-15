"""Application entrypoint helpers for ChromaMonitor."""

from .main_window import main as _main


def main() -> None:
    """Run the desktop application."""
    _main()
