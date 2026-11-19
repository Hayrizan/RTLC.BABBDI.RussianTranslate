#!/usr/bin/env python3
"""Check Russian coverage of BABBDI's serialized DialogueObject assets."""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

import UnityPy


# In BABBDI 1.2.4, DialogueObject's MonoBehaviour script PPtr uses path ID 1321.
DEFAULT_DIALOGUE_SCRIPT_PATH_ID = 1321
PLACEHOLDERS = {"...", "…"}


def read_aligned_string(data: bytes, offset: int) -> tuple[str, int]:
    if offset + 4 > len(data):
        raise ValueError("missing string length")
    length = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    if length > 1024 * 1024 or offset + length > len(data):
        raise ValueError(f"invalid string length {length}")
    value = data[offset:offset + length].decode("utf-8")
    offset = (offset + length + 3) & ~3
    return value, offset


def extract_dialogues(asset_path: Path, script_path_id: int) -> list[dict[str, object]]:
    environment = UnityPy.load(str(asset_path))
    records: list[dict[str, object]] = []
    for obj in environment.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) < 32:
            continue
        actual_script_path_id = struct.unpack_from("<q", raw, 20)[0]
        if actual_script_path_id != script_path_id:
            continue

        try:
            offset = 28
            name, offset = read_aligned_string(raw, offset)
            if offset + 4 > len(raw):
                raise ValueError("missing dialogue array length")
            count = struct.unpack_from("<i", raw, offset)[0]
            offset += 4
            if count < 0 or count > 1024:
                raise ValueError(f"invalid dialogue array length {count}")
            lines = []
            for _ in range(count):
                line, offset = read_aligned_string(raw, offset)
                lines.append(line)
            records.append({"path_id": obj.path_id, "name": name, "lines": lines})
        except (UnicodeDecodeError, ValueError, struct.error) as exception:
            raise ValueError(f"Could not decode DialogueObject path ID {obj.path_id}: {exception}") from exception

    if not records:
        raise ValueError(
            f"No DialogueObject records found in {asset_path}; script path ID {script_path_id} may be from another game build."
        )
    return records


def resolve_source(value: str, entries: dict[str, str]) -> bool:
    key = value.strip()
    if not key or key in PLACEHOLDERS:
        return True
    if key.casefold() in entries:
        return True

    match = re.match(r"^(.*?)(\s+\d+)$", key)
    return bool(match and match.group(1).casefold() in entries)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", required=True, type=Path, help="BABBDI installation directory")
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "translations" / "translations.json",
        help="translation catalog JSON",
    )
    parser.add_argument(
        "--script-path-id",
        type=int,
        default=DEFAULT_DIALOGUE_SCRIPT_PATH_ID,
        help="serialized Unity MonoBehaviour script PPtr path ID for DialogueObject",
    )
    args = parser.parse_args()

    asset_path = args.game_dir / "Babbdi_Data" / "sharedassets1.assets"
    catalog = json.loads(args.translations.read_text(encoding="utf-8"))
    entries = {
        str(entry["source"]).strip().casefold(): str(entry.get("target", ""))
        for entry in catalog.get("entries", [])
        if entry.get("source") is not None
    }
    records = extract_dialogues(asset_path, args.script_path_id)

    missing_names = []
    missing_lines = []
    nonblank = 0
    meaningful = 0
    for record in records:
        name = str(record["name"])
        if not resolve_source(name, entries):
            missing_names.append((record["path_id"], name))
        for line in record["lines"]:
            line = str(line)
            if not line.strip():
                continue
            nonblank += 1
            if line.strip() in PLACEHOLDERS:
                continue
            meaningful += 1
            if not resolve_source(line, entries):
                missing_lines.append((record["path_id"], name, line))

    print(f"DialogueObject records: {len(records)}")
    print(f"Nonblank line slots: {nonblank}; meaningful strings: {meaningful}")
    print(f"Missing speaker names: {len(missing_names)}")
    for path_id, name in missing_names:
        print(f"  #{path_id} speaker: {name!r}")
    print(f"Missing dialogue strings: {len(missing_lines)}")
    for path_id, name, line in missing_lines:
        print(f"  #{path_id} {name}: {line!r}")
    return 1 if missing_names or missing_lines else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exception:
        print(f"error: {exception}", file=sys.stderr)
        raise SystemExit(1)
