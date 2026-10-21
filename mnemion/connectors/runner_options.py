"""Shared, lightweight connector options for console and native engine entry points."""

from pathlib import Path

from ..version import __version__


def arguments(parser):
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--capture-control",
        action="store_true",
        help="Run a retained-capture control from bounded JSON on stdin; secrets use private references",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Read provider scope IDs and membership without importing or changing service access",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Repeat complete scans; configuration and token files reload between runs",
    )
    parser.add_argument(
        "--managed-state",
        type=Path,
        help="Use this local managed Linux/macOS service's verified runtime for each scan",
    )
