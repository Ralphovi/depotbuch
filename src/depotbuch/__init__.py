"""depotbuch: one portfolio across all brokers and deposits, net of taxes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("depotbuch")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
