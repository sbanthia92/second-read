"""Command-line interface: ``secondread review <file-or-url>``."""

from secondread.cli.main import ProgressPrinter, build_parser, main, run

__all__ = ["ProgressPrinter", "build_parser", "main", "run"]
