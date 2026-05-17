from pathlib import Path


def get_version() -> str:
    try:
        version_file = Path(__file__).parent.parent / "VERSION.txt"
        return version_file.read_text(encoding="utf-8").strip()
    except Exception:
        from cisco_config_generator.__about__ import __version__
        return __version__
