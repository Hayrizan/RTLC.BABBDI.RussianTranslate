"""Verify the BABBDI AssetBundle against the approved source files."""
import json
import sys
from pathlib import Path

import UnityPy

root = Path(__file__).resolve().parents[1]
source = root / "local_build/BepInEx/plugins/RTLC.BABBDI.RussianTranslate/Textures"
bundle = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "build/rtlc.bundle"
env = UnityPy.load(str(bundle))
assets = {name.rsplit("/", 1)[-1]: obj.read() for name, obj in env.container.items() if obj.type.name in ("Font", "TextAsset")}

def payload(name):
    value = assets[name].m_Script
    return value.encode("utf-8", "surrogateescape") if isinstance(value, str) else bytes(value)

assert payload("translations.bytes") == (root / "translations/translations.json").read_bytes()
original = json.loads((source / "texture_manifest.json").read_text(encoding="utf-8-sig"))
packed = json.loads(payload("texture_manifest.bytes").decode("utf-8-sig"))
assert len(original["textures"]) == len(packed["textures"])
for src, dst in zip(original["textures"], packed["textures"]):
    assert {**src, "file": dst["file"]} == dst
    assert (source / src["file"]).read_bytes() == payload(dst["file"]), src["file"]

fonts = ["FuturaHandwritten-Cyrillic-Regular.ttf", "MajorMonoDisplay-Cyrillic-Final-Regular.ttf"]
for font in fonts:
    assert bytes(assets[font.lower()].m_FontData) == (root / "assets/Fonts" / font).read_bytes(), font
assert len(assets) == len(fonts) + len(packed["textures"]) + 2
print(f"Verified {len(packed['textures'])} PNGs, {len(fonts)} fonts, catalog and manifest.")
