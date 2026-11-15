"""Constrained field types shared by the pack and workbook schemas.

Each type carries its own human-readable error message, so a bad value reads
the same whether it came from a pack YAML file or an Excel cell. The location
("settings.yaml: defaults.unused_vlan", "Sheet 'Devices', row 3, column 'Mgmt
IP'") is added by whoever formats the error - see friendly_message().
"""

from __future__ import annotations

import difflib
import ipaddress
import re
import types
import typing
from typing import Annotated, Any, Union

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

VLAN_ID_MIN = 1
VLAN_ID_MAX = 4094

# IOS accepts up to 63 characters; must start with a letter or digit and may
# contain letters, digits and hyphens.
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
_STORM_CONTROL_LEVEL_RE = re.compile(r"^\d+(?:\.\d+)?\s+\d+(?:\.\d+)?$")
_VLAN_LIST_ITEM_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def ranged_int(low: int, high: int, what: str = "Value") -> Any:
    """An int limited to low..high, with the range shown in the error and the JSON schema."""

    def check(value: int) -> int:
        if not low <= value <= high:
            raise ValueError(f"{what} {value} is out of range. Valid range: {low} to {high}.")
        return value

    return Annotated[
        int,
        AfterValidator(check),
        Field(json_schema_extra={"minimum": low, "maximum": high}),
    ]


def _check_ipv4(value: str) -> str:
    try:
        ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        raise ValueError(f"'{value}' is not a valid IPv4 address.") from None
    return value


def is_contiguous_mask(value: str) -> bool:
    """True for a dotted-decimal subnet mask such as 255.255.255.0."""
    try:
        bits = int(ipaddress.IPv4Address(value))
    except (ipaddress.AddressValueError, ValueError):
        return False
    # A valid mask is a run of 1 bits followed by a run of 0 bits.
    inverted = bits ^ 0xFFFFFFFF
    return ((inverted + 1) & inverted) == 0


def _check_subnet_mask(value: str) -> str:
    if not is_contiguous_mask(value):
        raise ValueError(
            f"'{value}' is not a valid dotted-decimal subnet mask, for example 255.255.255.0."
        )
    return value


def _check_hostname(value: str) -> str:
    if not _HOSTNAME_RE.fullmatch(value):
        raise ValueError(
            f"'{value}' is not a valid IOS hostname. "
            "Use up to 63 letters, digits or hyphens, starting with a letter or digit."
        )
    return value


def _check_storm_control_level(value: str) -> str:
    if not _STORM_CONTROL_LEVEL_RE.fullmatch(value):
        raise ValueError(
            f"'{value}' must contain two numeric values (rising and falling), for example '1.00 0.70'."
        )
    return value


def _check_optional_storm_control_level(value: str) -> str:
    return _check_storm_control_level(value) if value else value


def _check_optional_subnet_mask(value: str) -> str:
    return _check_subnet_mask(value) if value else value


def _check_optional_ipv4(value: str) -> str:
    return _check_ipv4(value) if value else value


def _normalise_vlan_list(value: str) -> str:
    """Check an IOS VLAN list such as '10,20,30-40' and drop any spaces.

    IOS rejects 'switchport trunk allowed vlan 10, 20', but that is how most
    people type a list into a spreadsheet cell.
    """
    compact = re.sub(r"\s+", "", value)
    if not compact:
        return ""
    for item in compact.split(","):
        match = _VLAN_LIST_ITEM_RE.fullmatch(item)
        if not match:
            raise ValueError(
                f"'{value}' is not a valid VLAN list. Use VLAN IDs and ranges separated "
                "by commas, for example '10,20,30-40'."
            )
        low = int(match.group(1))
        high = int(match.group(2) or low)
        for vlan_id in (low, high):
            if not VLAN_ID_MIN <= vlan_id <= VLAN_ID_MAX:
                raise ValueError(
                    f"VLAN list '{value}' contains VLAN {vlan_id}, which is out of range. "
                    f"Valid range: {VLAN_ID_MIN} to {VLAN_ID_MAX}."
                )
        if low > high:
            raise ValueError(f"VLAN list '{value}' contains the backwards range '{item}'.")
    return compact


def _normalise_allowed_vlans(value: str) -> str:
    if value.strip().lower() in ("all", "none"):
        return value.strip().lower()
    return _normalise_vlan_list(value)


def _split_comma_list(value: Any) -> Any:
    """Accept '10.0.0.1, 10.0.0.2' from a spreadsheet cell as well as a real list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


VlanId = ranged_int(VLAN_ID_MIN, VLAN_ID_MAX, "VLAN")
PrivilegeLevel = ranged_int(0, 15, "Privilege level")
TcpUdpPort = ranged_int(1, 65535, "Port")

IPv4 = Annotated[str, AfterValidator(_check_ipv4)]
SubnetMask = Annotated[str, AfterValidator(_check_subnet_mask)]
Hostname = Annotated[str, AfterValidator(_check_hostname)]
StormControlLevel = Annotated[
    str,
    AfterValidator(_check_storm_control_level),
    Field(json_schema_extra={"pattern": _STORM_CONTROL_LEVEL_RE.pattern}),
]
# Blank means "use the pack default" for a workbook cell.
OptionalStormControlLevel = Annotated[
    str,
    AfterValidator(_check_optional_storm_control_level),
]
OptionalIPv4 = Annotated[str, AfterValidator(_check_optional_ipv4)]
OptionalSubnetMask = Annotated[str, AfterValidator(_check_optional_subnet_mask)]
VlanList = Annotated[str, AfterValidator(_normalise_vlan_list)]
# A trunk's allowed list also takes the IOS keywords 'all' and 'none'.
AllowedVlans = Annotated[str, AfterValidator(_normalise_allowed_vlans)]
IPv4List = Annotated[list[IPv4], BeforeValidator(_split_comma_list)]


# ---------------------------------------------------------------------------
# Error formatting
# ---------------------------------------------------------------------------
def friendly_message(
    error: dict[str, Any],
    model: type[BaseModel] | None = None,
    noun: str = "setting",
) -> str:
    """Turn one pydantic error into a sentence a network engineer can act on.

    The caller prefixes the location. ``model`` is the root model that was
    validated; when given, an unknown key is answered with the closest real
    field name, so 'ssh_timout' suggests 'ssh_timeout'.
    """
    kind = error["type"]
    value = error.get("input")
    ctx = error.get("ctx") or {}
    if kind == "value_error":
        # Our own validators: the message is already written for a person.
        return str(ctx.get("error", error["msg"]))
    if kind == "missing":
        return "is required."
    if kind == "extra_forbidden":
        message = f"is not a recognised {noun}."
        if model is not None:
            suggestion = _closest_field(model, error["loc"])
            if suggestion:
                message += f" Did you mean '{suggestion}'?"
        return message + " Check the spelling, or remove it."
    if kind == "literal_error":
        return f"is '{value}'. Valid values: {ctx.get('expected', '')}."
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return f"expected a whole number, got '{value}'."
    if kind in ("bool_parsing", "bool_type"):
        return f"expected Yes/No (or true/false), got '{value}'."
    if kind in ("string_type",):
        return f"expected text, got '{value}'."
    if kind == "string_pattern_mismatch":
        return f"is '{value}', which is not in the expected format (pattern {ctx.get('pattern', '')})."
    if kind in ("list_type",):
        return f"expected a list, got '{value}'."
    if kind in ("dict_type", "model_type", "model_attributes_type"):
        return f"expected a mapping of settings, got '{value}'."
    return f"{error['msg']} (got '{value}')."


def _closest_field(model: type[BaseModel], loc: tuple) -> str | None:
    """The field name nearest to an unknown key, for 'did you mean' hints."""
    owner = _type_at(model, loc[:-1])
    if not (isinstance(owner, type) and issubclass(owner, BaseModel)):
        return None
    matches = difflib.get_close_matches(str(loc[-1]), list(owner.model_fields), n=1, cutoff=0.6)
    return matches[0] if matches else None


def _type_at(model: type[BaseModel], path: tuple) -> Any:
    """Follow an error location from the root model down to the type it points at."""
    current: Any = model
    for part in path:
        current = _unwrap(current)
        if isinstance(current, type) and issubclass(current, BaseModel):
            field = current.model_fields.get(str(part))
            if field is None:
                return None
            current = field.annotation
            continue
        origin = typing.get_origin(current)
        args = typing.get_args(current)
        if origin is dict and len(args) == 2:
            current = args[1]
        elif origin is list and args:
            current = args[0]
        else:
            return None
    return _unwrap(current)


def _unwrap(annotation: Any) -> Any:
    """Strip Annotated[...] and Optional[...] wrappers."""
    while True:
        origin = typing.get_origin(annotation)
        if origin is Annotated:
            annotation = typing.get_args(annotation)[0]
        elif origin in (Union, types.UnionType):
            options = [a for a in typing.get_args(annotation) if a is not type(None)]
            if len(options) != 1:
                return annotation
            annotation = options[0]
        else:
            return annotation


def format_loc(loc: tuple) -> str:
    """('defaults', 'aaa', 'authorization', 'commands', 0) -> defaults.aaa.authorization.commands[0]"""
    text = ""
    for part in loc:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else str(part)
    return text


def join_location(location: str, message: str) -> str:
    """'defaults.ssh_timout' + 'is not a recognised setting.' -> one sentence.

    Messages that continue the sentence ('is required.') follow the location
    directly; complete sentences ('VLAN 5000 is out of range.') get a colon.
    """
    if message[:1].islower():
        return f"{location} {message}"
    return f"{location}: {message}"
