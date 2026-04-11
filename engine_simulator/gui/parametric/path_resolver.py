"""Dotted/indexed/wildcard path resolver for the engine config dict.

Supports three path syntaxes:
- "plenum.volume"           — dotted
- "intake_pipes[0].length"  — indexed list access
- "intake_pipes[*].length"  — wildcard (applies to all list elements)

get_parameter() returns the value(s). set_parameter() returns a deep copy
with the mutation applied — the input dict is never touched.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Optional


class PathError(ValueError):
    """Raised when a path is malformed or does not resolve."""


class BoundsError(ValueError):
    """Raised when a value is outside the allowed bounds for a parameter."""


# Matches a path segment like "foo", "foo[0]", or "foo[*]".
_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+|\*)\])?$")


def _parse_path(path: str) -> list[tuple[str, Optional[str]]]:
    """Parse 'a.b[0].c' into [('a', None), ('b', '0'), ('c', None)]."""
    if not path:
        raise PathError("empty path")
    segments = []
    for raw in path.split("."):
        match = _SEGMENT_RE.match(raw)
        if not match:
            raise PathError(f"invalid path segment: {raw!r}")
        name, index = match.group(1), match.group(2)
        segments.append((name, index))
    return segments


def _descend(obj: Any, segments: list[tuple[str, Optional[str]]]) -> Any:
    """Walk `segments` into `obj`, returning the resolved value or list
    of values (for wildcard). Read-only."""
    if not segments:
        return obj
    name, index = segments[0]
    rest = segments[1:]

    if not isinstance(obj, dict) or name not in obj:
        raise PathError(f"missing key: {name}")

    child = obj[name]

    if index is None:
        return _descend(child, rest)

    if not isinstance(child, list):
        raise PathError(f"expected list at {name}, got {type(child).__name__}")

    if index == "*":
        return [_descend(item, rest) for item in child]

    idx = int(index)
    if idx < 0 or idx >= len(child):
        raise PathError(f"index {idx} out of range for {name}")

    return _descend(child[idx], rest)


def _apply(obj: Any, segments: list[tuple[str, Optional[str]]], value: float) -> None:
    """Write `value` at the location indicated by `segments`. Mutates `obj`
    in place — the caller provides a deep copy."""
    if not segments:
        raise PathError("empty path for set")

    name, index = segments[0]
    rest = segments[1:]

    if not isinstance(obj, dict) or name not in obj:
        raise PathError(f"missing key: {name}")

    if index is None:
        if not rest:
            obj[name] = value
            return
        _apply(obj[name], rest, value)
        return

    child = obj[name]
    if not isinstance(child, list):
        raise PathError(f"expected list at {name}, got {type(child).__name__}")

    if index == "*":
        for item in child:
            if not rest:
                raise PathError(f"wildcard requires a trailing field: {name}[*]")
            _apply(item, rest, value)
        return

    idx = int(index)
    if idx < 0 or idx >= len(child):
        raise PathError(f"index {idx} out of range for {name}")

    if not rest:
        child[idx] = value
        return
    _apply(child[idx], rest, value)


def get_parameter(config: dict, path: str) -> Any:
    """Read the value at `path`. For wildcard paths, returns a list."""
    segments = _parse_path(path)
    return _descend(config, segments)


def set_parameter(
    config: dict,
    path: str,
    value: float,
    min_allowed: Optional[float] = None,
    max_allowed: Optional[float] = None,
) -> dict:
    """Return a deep copy of `config` with `value` written at `path`.

    If `min_allowed` / `max_allowed` are provided, raises BoundsError when
    `value` is out of range. The input `config` is never mutated.
    """
    if min_allowed is not None and value < min_allowed:
        raise BoundsError(f"{value} below min_allowed={min_allowed}")
    if max_allowed is not None and value > max_allowed:
        raise BoundsError(f"{value} above max_allowed={max_allowed}")

    segments = _parse_path(path)
    new_config = copy.deepcopy(config)
    _apply(new_config, segments, value)
    return new_config
