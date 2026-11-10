"""`depot`: the command-line interface, a thin entry point over Django's management
commands, so the CLI and the web API run against the same engine.
"""

import os
import sys

from django.core.management import execute_from_command_line


def main(argv: list[str] | None = None) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "depotbuch.web.settings")
    execute_from_command_line(sys.argv if argv is None else argv)
