from __future__ import annotations

import json
from typing import Any


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("NaN and infinity are not valid configuration values")
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value: {type(value).__name__}")


def dumps(data: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_table(table: dict[str, Any], path: list[str], array_header: bool = False) -> None:
        if path:
            header = ".".join(path)
            lines.append(f"[[{header}]]" if array_header else f"[{header}]")
        for key, value in table.items():
            if not isinstance(value, dict) and not (isinstance(value, list) and value and all(isinstance(x, dict) for x in value)):
                lines.append(f"{key} = {_value(value)}")
        if path or lines:
            lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                emit_table(value, path + [key])
            elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
                for item in value:
                    emit_table(item, path + [key], array_header=True)

    emit_table(data, [])
    return "\n".join(lines).rstrip() + "\n"
