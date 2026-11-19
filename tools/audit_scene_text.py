#!/usr/bin/env python3
"""Audit serialized UI strings in BABBDI 1.2.4's built-in scenes.

UnityPy reads the shared MonoBehaviour header, but this build strips the UI
component type trees. The two offsets below are the serialized m_text fields
for TextMeshProUGUI and UnityEngine.UI.Text in this game's Unity 2022.1.5f1
scene files. The string payload is a 32-bit byte length followed by UTF-8.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import UnityPy


TEXT_OFFSETS = {
    "TextMeshProUGUI": 88,
    "Text": 144,
}
SCENES = ("level0", "level1")
EXTRA_ASSETS = ("level0", "level1", "sharedassets0.assets", "sharedassets1.assets")
# These values are embedded deliberately: product/version branding, a physical
# input token, and initial placeholders that runtime library counters replace.
RETAINED_STRINGS = {
    "babbdi": "game title / brand",
    "version 1.2.4": "game version",
    "[e]": "physical input key",
    "new text": "serialized placeholder for runtime library counters",
}


def read_tree(obj: Any) -> dict[str, Any]:
    return obj.read_typetree(check_read=False)


def load_script_names(data_dir: Path) -> dict[int, str]:
    env = UnityPy.load(str(data_dir / "globalgamemanagers.assets"))
    result: dict[int, str] = {}
    for obj in env.objects:
        if obj.type.name != "MonoScript":
            continue
        try:
            tree = read_tree(obj)
        except Exception:
            continue
        class_name = tree.get("m_ClassName")
        if class_name:
            result[obj.path_id] = str(class_name)
    return result


def decode_text(raw: bytes, offset: int, context: str) -> str:
    if offset + 4 > len(raw):
        raise ValueError(f"{context}: m_text length is outside the component data")
    size = struct.unpack_from("<I", raw, offset)[0]
    start = offset + 4
    end = start + size
    if size > len(raw) or end > len(raw):
        raise ValueError(f"{context}: invalid m_text byte length {size}")
    return raw[start:end].decode("utf-8", errors="strict")


def read_aligned_string(raw: bytes, offset: int, context: str) -> tuple[str, int]:
    if offset + 4 > len(raw):
        raise ValueError(f"{context}: string length outside data at {offset}")
    size = struct.unpack_from("<I", raw, offset)[0]
    start = offset + 4
    end = start + size
    if size > len(raw) or end > len(raw):
        raise ValueError(f"{context}: invalid string length {size} at {offset}")
    text = raw[start:end].decode("utf-8", errors="strict")
    return text, (end + 3) & ~3


def extract_custom_texts(
    asset_name: str,
    class_name: str,
    raw: bytes,
    context: str,
) -> list[tuple[str, str]]:
    """Extract serialised UI/gameplay strings from custom BABBDI components."""
    results: list[tuple[str, str]] = []
    if class_name == "TextPrompt":
        _, off = read_aligned_string(raw, 28, context)
        off += 12  # textLabel PPtr
        normal_text, off = read_aligned_string(raw, off, context)
        gamepad_text, _ = read_aligned_string(raw, off, context)
        if normal_text.strip():
            results.append(("TextPrompt.normalText", normal_text))
        if gamepad_text.strip():
            results.append(("TextPrompt.gamepadText", gamepad_text))
    elif class_name == "DialogueUI":
        _, off = read_aligned_string(raw, 28, context)
        speaker_name, _ = read_aligned_string(raw, off, context)
        if speaker_name.strip():
            results.append(("DialogueUI.name", speaker_name))
    elif class_name == "Trumpet":
        _, off = read_aligned_string(raw, 28, context)
        off += 4  # scaleIndex
        for _ in range(3):  # scaleFactor, scaleDecal, scaleLimit
            count = struct.unpack_from("<i", raw, off)[0]
            off += 4
            if count < 0 or count > 256 or off + count * 4 > len(raw):
                raise ValueError(f"{context}: invalid float array length {count}")
            off += count * 4
        off += 12  # scalePopup PPtr
        count = struct.unpack_from("<i", raw, off)[0]
        off += 4
        if count < 0 or count > 256:
            raise ValueError(f"{context}: invalid scaleName length {count}")
        for _ in range(count):
            scale_label, off = read_aligned_string(raw, off, context)
            if scale_label.strip():
                results.append(("Trumpet.scaleName", scale_label))
    elif class_name == "TMP_Dropdown" and asset_name in SCENES:
        # Selectable (m_Name + Navigation + Transition + ColorBlock + SpriteState + AnimationTriggers)
        # ends at offset 384 in Unity 2022.1.5 TMP_Dropdown; verify Disabled trigger then read options.
        _, off = read_aligned_string(raw, 28, context)
        # Scan aligned offsets for the OptionDataList count after Selectable's "Disabled" trigger.
        disabled_pos = raw.find(b"\x08\x00\x00\x00Disabled")
        if disabled_pos < 0:
            raise ValueError(f"{context}: could not locate AnimationTriggers in TMP_Dropdown")
        # After "Disabled" (12 bytes): m_Interactable(4) + m_TargetGraphic(12) +
        # m_Template(12) + m_CaptionText(12) + m_CaptionImage(12) + m_Placeholder(12) +
        # m_ItemText(12) + m_ItemImage(12) + m_Value(4) = 92 bytes -> m_Options.m_Options count
        off = disabled_pos + 12 + 92
        count = struct.unpack_from("<i", raw, off)[0]
        off += 4
        if count < 0 or count > 128:
            raise ValueError(f"{context}: invalid TMP_Dropdown option count {count}")
        for _ in range(count):
            opt_text, off = read_aligned_string(raw, off, context)
            off += 12  # OptionData.m_Image Sprite PPtr
            if opt_text.strip():
                results.append(("TMP_Dropdown.option", opt_text))
    return results


def extract_scene_text(data_dir: Path, scripts: dict[int, str]) -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for asset_name in EXTRA_ASSETS:
        env = UnityPy.load(str(data_dir / asset_name))
        game_objects: dict[int, str] = {}
        for obj in env.objects:
            if obj.type.name == "GameObject":
                try:
                    tree = read_tree(obj)
                    game_objects[obj.path_id] = str(tree.get("m_Name", ""))
                except Exception:
                    continue

        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                tree = read_tree(obj)
                script = tree.get("m_Script") or {}
                class_name = scripts.get(script.get("m_PathID"))
                if not class_name:
                    continue
                game_object = tree.get("m_GameObject") or {}
                owner = game_objects.get(game_object.get("m_PathID"), "")
                context = f"{asset_name} MonoBehaviour #{obj.path_id} ({owner}, {class_name})"
                raw = obj.get_raw_data()

                offset = TEXT_OFFSETS.get(class_name) if asset_name in SCENES else None
                if offset is not None:
                    text = decode_text(raw, offset, context)
                    if text.strip():
                        rows.append({
                            "scene": asset_name,
                            "path_id": obj.path_id,
                            "game_object": owner,
                            "component": class_name,
                            "text": text,
                        })
                elif class_name in ("TextPrompt", "DialogueUI", "Trumpet", "TMP_Dropdown"):
                    for sub_component, text in extract_custom_texts(asset_name, class_name, raw, context):
                        rows.append({
                            "scene": asset_name,
                            "path_id": obj.path_id,
                            "game_object": owner,
                            "component": sub_component,
                            "text": text,
                        })
            except Exception as exc:
                print(f"warning: could not inspect {asset_name} MonoBehaviour #{obj.path_id}: {exc}", file=sys.stderr)
    return rows


def is_translated(text: str, translations: dict[str, str]) -> bool:
    key = text.strip().casefold()
    if key in translations:
        return True
    colon = key.find(":")
    return colon > 0 and key[:colon].rstrip() in translations


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True, help="BABBDI installation directory")
    parser.add_argument(
        "--translations",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "translations" / "translations.json",
    )
    parser.add_argument("--json", type=Path, help="write the full extracted component list to this JSON file")
    args = parser.parse_args()

    data_dir = args.game_dir / "Babbdi_Data"
    if not (data_dir / "globalgamemanagers.assets").is_file():
        data_dir = args.game_dir
    if not (data_dir / "globalgamemanagers.assets").is_file():
        parser.error(f"could not find globalgamemanagers.assets under {args.game_dir}")

    catalog_data = json.loads(args.translations.read_text(encoding="utf-8"))
    translations = {
        str(entry["source"]).strip().casefold(): str(entry["target"])
        for entry in catalog_data.get("entries", [])
        if entry.get("source") and entry.get("target") is not None
    }
    scripts = load_script_names(data_dir)
    rows = extract_scene_text(data_dir, scripts)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    unique: dict[str, str] = {}
    for row in rows:
        text = str(row["text"])
        unique.setdefault(text, str(row["text"]).strip().casefold())
    missing = [source for source, key in unique.items()
               if key not in RETAINED_STRINGS and not is_translated(source, translations)]
    retained = [source for source, key in unique.items() if key in RETAINED_STRINGS]
    print(f"Scene text components: {len(rows)}")
    print(f"Unique nonblank strings: {len(unique)}")
    print(f"Explicitly retained strings: {len(retained)}")
    for source in retained:
        print(f"- retained {source!r}: {RETAINED_STRINGS[unique[source]]}")
    print(f"Unmatched exact strings: {len(missing)}")
    for source in missing:
        owners = [
            f"{row['scene']}#{row['path_id']} {row['game_object']}"
            for row in rows if row["text"] == source
        ]
        print(f"- {source!r} ({'; '.join(owners)})")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
