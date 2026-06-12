"""
Minimal output-shape validation for agent results. Each agent declares a SCHEMA:
``{key: type}`` (use ``list``/``dict``/``str``/``int``/``float`` for the expected
type, or a tuple of acceptable types). ``validate_shape`` checks every required key
is present with the right type and returns ``(ok, errors)``. Deliberately tiny — a
full JSON-Schema lib is unnecessary for the fixed agent contracts and avoids a
dependency; the gateway rejects a malformed LLM output rather than passing it on.
"""
from __future__ import annotations


def validate_shape(content, schema) -> tuple[bool, list]:
    errors = []
    if not isinstance(content, dict):
        return False, ["content is not an object"]
    for key, expected in schema.items():
        if key not in content:
            errors.append(f"missing key '{key}'")
            continue
        if not isinstance(content[key], expected):
            type_name = (
                "/".join(t.__name__ for t in expected)
                if isinstance(expected, tuple)
                else expected.__name__
            )
            errors.append(f"key '{key}' must be {type_name}")
    return (not errors), errors
