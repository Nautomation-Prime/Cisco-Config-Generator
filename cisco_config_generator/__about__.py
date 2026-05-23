from importlib.metadata import version as _version, PackageNotFoundError as _PackageNotFoundError

__title__ = "cisco-config-generator"
__description__ = "Cisco IOS-XE access switch configuration generator"
__author__ = "Nautomation Prime"
__license__ = "MIT"

try:
    __version__ = _version("cisco-config-generator")
except _PackageNotFoundError:
    __version__ = "unknown"
