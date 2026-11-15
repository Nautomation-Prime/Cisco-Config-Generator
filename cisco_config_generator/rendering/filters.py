"""Jinja filters shared by the config templates.

Keeps IOS command grammar that needs real logic (rather than a substitution)
out of the templates themselves, so it can be unit tested.
"""

from __future__ import annotations

import re

# Prefixes IOS uses for already-hashed secrets, mapped to the secret type
# number that must be quoted back when the value is re-applied.
_HASH_PREFIX_TO_TYPE: dict[str, str] = {
    "$9$": "9",   # scrypt
    "$8$": "8",   # PBKDF2-SHA-256
    "$1$": "5",   # MD5
}

# 'algorithm-type' keywords accepted by 'enable' / 'username' when the switch
# is asked to hash a plaintext password itself.
_HASH_TYPE_KEYWORD: dict[str, str] = {
    "scrypt": "scrypt",
    "sha256": "sha256",
    "md5": "md5",
}

_TYPE7_RE = re.compile(r"^[0-9A-Fa-f]{4,}$")


def is_hashed_secret(value: str) -> bool:
    """True when the value is already an IOS password hash ($9$..., $8$..., $1$...)."""
    return any(str(value).startswith(prefix) for prefix in _HASH_PREFIX_TO_TYPE)


def cisco_secret(value: str, hash_type: str = "scrypt") -> str:
    """Render the secret portion of an 'enable' or 'username' command.

    A value that is already hashed is quoted back with its own type number.
    A plaintext value is handed to the switch with 'algorithm-type <type>' so
    the switch does the hashing — writing 'secret 9 <plaintext>' would be
    rejected, because type 9 expects a scrypt hash rather than a password.

        >>> cisco_secret("MyPassw0rd")
        'algorithm-type scrypt secret MyPassw0rd'
        >>> cisco_secret("$9$salt$hash")
        'secret 9 $9$salt$hash'
    """
    text = str(value)
    for prefix, secret_type in _HASH_PREFIX_TO_TYPE.items():
        if text.startswith(prefix):
            return f"secret {secret_type} {text}"

    keyword = _HASH_TYPE_KEYWORD.get(str(hash_type).strip().lower())
    if keyword is None:
        raise ValueError(
            f"Unknown password_hash_type '{hash_type}'. "
            f"Valid values: {', '.join(sorted(_HASH_TYPE_KEYWORD))}."
        )
    return f"algorithm-type {keyword} secret {text}"


def looks_like_type7(value: str) -> bool:
    """True when the value has the shape of a type 7 encrypted string."""
    text = str(value).strip()
    return bool(_TYPE7_RE.fullmatch(text)) and len(text) % 2 == 0


def starts_with_any(value: str, prefixes: list[str]) -> bool:
    """True when value starts with any of the given prefixes.

    Used to spot uplink-speed interfaces by name without hard-coding a single
    prefix in every trunk template.
    """
    text = str(value)
    return any(text.startswith(str(prefix)) for prefix in prefixes or [])


FILTERS = {
    "cisco_secret": cisco_secret,
    "is_hashed_secret": is_hashed_secret,
    "starts_with_any": starts_with_any,
}
