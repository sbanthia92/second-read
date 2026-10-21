"""Command-line interface: ``reviewdesk review <file-or-url>``."""

from reviewdesk.cli.main import ProgressPrinter, build_parser, main, run

__all__ = ["ProgressPrinter", "build_parser", "main", "run"]
