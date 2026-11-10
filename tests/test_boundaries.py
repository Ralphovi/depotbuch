"""The engine and adapters must run without Django (spec, Architecture rules).

ruff's banned-api rule catches a direct import; this catches a transitive one, by
importing each package in a fresh interpreter and checking what got loaded.
"""

import subprocess
import sys

import pytest

FRAMEWORK_MODULES = ("django", "ninja")


@pytest.mark.parametrize("package", ["depotbuch.engine", "depotbuch.adapters"])
def test_package_loads_without_a_framework(package: str) -> None:
    code = (
        f"import sys, {package}\n"
        f"loaded = sorted(m for m in sys.modules if m.split('.')[0] in {FRAMEWORK_MODULES!r})\n"
        "print(','.join(loaded))"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
