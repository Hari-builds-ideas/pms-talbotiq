"""
Minimal output-shape validation for agent results. Each agent declares a SCHEMA;
``validate_shape`` checks it and returns ``(ok, errors)``. Deliberately tiny — a
full JSON-Schema lib is unnecessary for the fixed agent contracts and avoids a
dependency; the gateway rejects a malformed LLM output rather than passing it on.

A schema is a ``{key: spec}`` mapping. A ``spec`` is one of:
  * a **type** (``str`` / ``int`` / ``list`` / ``dict`` …) — value must be that type;
  * a **tuple of types** — value must be one of them;
  * a **nested dict** ``{subkey: spec}`` — value must be an object matching it
    (recursively) — used to pin each required *section* of a multi-section answer;
  * a :class:`NonEmpty` marker — value must be a non-blank string (≥ ``min_len``
    chars after stripping). This is the quality floor that makes a blank / null /
    whitespace "section" fail validation (the gateway returns ``SCHEMA_INVALID``
    rather than handing a hollow draft to a human) — the per-agent prompt + the
    confidence heuristic handle thin-but-present content as low-confidence.
"""
from __future__ import annotations


class NonEmpty:
    """Schema marker: a non-blank string of at least ``min_len`` characters after
    stripping. Default ``min_len=1`` rejects empty / whitespace-only values; raise
    it per field to demand a little substance without hard-failing terse answers."""

    __slots__ = ("min_len",)

    def __init__(self, min_len: int = 1):
        self.min_len = min_len

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"NonEmpty(min_len={self.min_len})"


class ListOf:
    """Schema marker: a NON-EMPTY list (>= ``min_len`` items) whose every item matches
    ``item_spec`` (default: a non-blank string). An empty OR absent list fails — a
    required list with nothing in it is a hollow answer, not a valid one (audit
    Finding D), so the gateway returns ``SCHEMA_INVALID`` rather than handing a human
    e.g. zero ``action_items`` / ``tiers`` / ``responsibilities``. Item-shape is
    enforced too, so a list of objects where strings are expected also fails."""

    __slots__ = ("item_spec", "min_len")

    def __init__(self, item_spec=None, min_len: int = 1):
        self.item_spec = item_spec if item_spec is not None else NonEmpty(1)
        self.min_len = min_len

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"ListOf({self.item_spec!r}, min_len={self.min_len})"


def _check(value, spec, path: str, errors: list) -> None:
    if isinstance(spec, NonEmpty):
        if not isinstance(value, str) or len(value.strip()) < spec.min_len:
            errors.append(
                f"key '{path}' must be a non-empty string (>= {spec.min_len} chars)"
            )
        return
    if isinstance(spec, ListOf):
        if not isinstance(value, list) or len(value) < spec.min_len:
            errors.append(
                f"key '{path}' must be a non-empty list (>= {spec.min_len} items)"
            )
            return
        for i, item in enumerate(value):
            _check(item, spec.item_spec, f"{path}[{i}]", errors)
        return
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            errors.append(f"key '{path}' must be an object")
            return
        for subkey, subspec in spec.items():
            if subkey not in value:
                errors.append(f"missing key '{path}.{subkey}'")
                continue
            _check(value[subkey], subspec, f"{path}.{subkey}", errors)
        return
    # A bare type or a tuple of acceptable types.
    if not isinstance(value, spec):
        type_name = (
            "/".join(t.__name__ for t in spec)
            if isinstance(spec, tuple)
            else spec.__name__
        )
        errors.append(f"key '{path}' must be {type_name}")


def validate_shape(content, schema) -> tuple[bool, list]:
    errors: list = []
    if not isinstance(content, dict):
        return False, ["content is not an object"]
    for key, spec in schema.items():
        if key not in content:
            errors.append(f"missing key '{key}'")
            continue
        _check(content[key], spec, key, errors)
    return (not errors), errors
