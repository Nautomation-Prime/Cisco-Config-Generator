"""Package metadata for Cisco Config Generator."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version

from .version import get_version

__title__ = "cisco-config-generator"
__app_name__ = __title__
__description__ = "Cisco IOS-XE access switch configuration generator"
__license__ = "MIT"
__author__ = "Christopher Davies"

try:
    __version__ = package_version(__title__)
except PackageNotFoundError:
    __version__ = get_version()
