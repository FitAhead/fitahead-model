#!/usr/bin/env python3
"""Generate the FitAhead character GLBs and their runtime manifest.

    python3 tools/gen_character.py                 # writes assets/models/
    python3 tools/gen_character.py --preset female
    python3 tools/gen_character.py --out build/

No third-party dependencies: the glTF and PNG writers are in fitahead_gen/.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fitahead_gen import export, manifest, params, png  # noqa: E402
from fitahead_gen.body import Character  # noqa: E402

DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "models"
)
FACE_TEXTURE = "face_default.png"


def generate(out_dir, preset_names, face_size):
    os.makedirs(out_dir, exist_ok=True)

    face_png = png.default_face(size=face_size)
    with open(os.path.join(out_dir, FACE_TEXTURE), "wb") as f:
        f.write(face_png)

    presets = {}
    for name in preset_names:
        preset = params.PRESETS[name]
        character = Character(preset)
        filename = f"{name}.glb"
        result = export.export_glb(
            character, os.path.join(out_dir, filename), face_png
        )
        presets[name] = manifest.build_manifest(
            character, filename, result["meshes"], FACE_TEXTURE
        )
        stats = character.stats()
        sparse = result["sparseTargets"]
        print(f"{filename:14s} {result['bytes'] / 1024:8.1f} KB  "
              f"{stats['vertices']:6d} verts  {stats['triangles']:6d} tris  "
              f"{stats['joints']:2d} joints  "
              f"{stats['morphTargets']:2d} morphs "
              f"({stats['muscleGroups']} muscle)  "
              f"{sparse['sparse']}/{sparse['targets']} sparse")

    doc = {
        "version": 1,
        "generator": "tools/gen_character.py",
        "faceTexture": FACE_TEXTURE,
        "presets": presets,
    }
    path = os.path.join(out_dir, "character_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{'manifest':14s} {os.path.getsize(path) / 1024:8.1f} KB  -> {path}")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--preset", action="append", choices=sorted(params.PRESETS),
                    help="preset to build (repeatable; default: all)")
    ap.add_argument("--face-size", type=int, default=512,
                    help="placeholder face texture resolution")
    args = ap.parse_args(argv)

    generate(args.out, args.preset or sorted(params.PRESETS), args.face_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
