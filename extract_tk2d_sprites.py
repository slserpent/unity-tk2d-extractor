"""
extract_tk2d_sprites.py
Extract individual sprites from an exported tk2d sprite atlas.
Reads a tk2dSpriteCollectionData JSON and a matching atlas texture, outputs one PNG per sprite.

Requirements:
    Python 3.8+
    pip install Pillow

Usage:
    python extract_sprites.py <collection.json> <atlas> [options]

Arguments:
    collection        Exported tk2dSpriteCollectionData JSON from Asset Studio
    atlas             Exported atlas texture (PNG recommended; path matched manually or by path ID)
    --output DIR      Output directory for extracted sprite PNGs (default: spriteCollectionName from JSON)
    --material-id N   Only extract sprites with materialId N; use for multi-atlas collections (default: all)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image

ILLEGAL_NAME_CHARS = re.compile(r'[/\\:*?"<>|]')


def sanitize(name):
    return ILLEGAL_NAME_CHARS.sub('_', name)


def extract_sprites(collection_path, atlas_path, output_dir, material_id=None):
    # load sprite collection JSON
    with open(collection_path, encoding='utf-8') as f:
        collection = json.load(f)

    # warn if the data format version is unexpected
    version = collection.get('version')
    if version != 3:
        print(f"Warning: unexpected collection version {version!r} (expected 3) — output may be incorrect", file=sys.stderr)

    # default output directory to the collection's own name
    if output_dir is None:
        output_dir = sanitize(collection.get('spriteCollectionName', 'output'))

    # load atlas texture and record its pixel dimensions
    atlas = Image.open(atlas_path)
    atlas_w, atlas_h = atlas.size

    os.makedirs(output_dir, exist_ok=True)

    # optionally filter to a single material's sprites for multi-atlas collections
    sprites = collection.get('spriteDefinitions', [])
    if material_id is not None:
        sprites = [s for s in sprites if s.get('materialId', 0) == material_id]
    total = len(sprites)

    for idx, sprite in enumerate(sprites, 1):
        # unpack sprite definition fields
        name = sprite.get('name', '')
        uvs = sprite.get('uvs', [])
        positions = sprite.get('positions', [])
        indices = sprite.get('indices', [])
        flipped = sprite.get('flipped', 0)

        # skip invalid/placeholder entries (no name or no geometry)
        if not name:
            print(f"[{idx}/{total}] skipped (no name)", file=sys.stderr)
            continue

        if not uvs:
            print(f"[{idx}/{total}] {name}: skipped (no UVs)", file=sys.stderr)
            continue

        # size the output canvas from the bounding box of all mesh vertex positions
        pos_xs = [p['x'] for p in positions]
        pos_ys = [p['y'] for p in positions]
        global_min_x = min(pos_xs)
        global_max_y = max(pos_ys)
        canvas_w = round(max(pos_xs) - global_min_x)
        canvas_h = round(global_max_y - min(pos_ys))

        canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))

        # 6 indices per quad (2 triangles); reconstruct and paste one quad at a time
        for qi in range(0, len(indices), 6):
            quad_verts = sorted(set(indices[qi:qi + 6]))

            quad_uvs = [uvs[vi] for vi in quad_verts]
            quad_pos = [positions[vi] for vi in quad_verts]

            # crop quad tile from atlas; UV y=0 is bottom, so invert Y for Pillow
            uv_xs = [uv['x'] for uv in quad_uvs]
            uv_ys = [uv['y'] for uv in quad_uvs]
            left  = min(uv_xs) * atlas_w
            right = max(uv_xs) * atlas_w
            upper = (1.0 - max(uv_ys)) * atlas_h
            lower = (1.0 - min(uv_ys)) * atlas_h
            tile = atlas.crop((left, upper, right, lower))

            # unpack sprite-level atlas rotation if present
            if flipped == 1:    # Tk2d internal packer rotation
                tile = tile.transpose(Image.Transpose.TRANSVERSE)
            elif flipped == 2:  # TexturePacker CW rotation
                tile = tile.transpose(Image.Transpose.ROTATE_90)

            # destination rect in canvas space; positions are Unity Y-up, canvas is Y-down
            qp_xs = [p['x'] for p in quad_pos]
            qp_ys = [p['y'] for p in quad_pos]
            dest_left   = round(min(qp_xs) - global_min_x)
            dest_top    = round(global_max_y - max(qp_ys))
            dest_right  = round(max(qp_xs) - global_min_x)
            dest_bottom = round(global_max_y - min(qp_ys))

            # transposed tile dimensions mean this quad was packed rotated independently
            dest_w = dest_right - dest_left
            dest_h = dest_bottom - dest_top
            if dest_w != dest_h and tile.size == (dest_h, dest_w):
                tile = tile.transpose(Image.Transpose.TRANSVERSE)
            elif tile.size != (dest_w, dest_h):
                tile = tile.resize((dest_w, dest_h), Image.NEAREST)

            canvas.paste(tile, (dest_left, dest_top))

        # save finished sprite to output directory
        out_path = Path(output_dir) / f"{sanitize(name)}.png"
        try:
            canvas.save(out_path)
        except Exception as e:
            print(f"[{idx}/{total}] {name}: failed to save '{out_path}': {e}", file=sys.stderr)
            continue
        print(f"[{idx}/{total}] {name} ({canvas_w}x{canvas_h}) extracted successfully")

    print(f"\nDone. {total} sprites extracted to '{output_dir}'")


def main():
    parser = argparse.ArgumentParser(description='Extract sprites from a tk2d sprite atlas.')
    parser.add_argument('collection', nargs='?', help='Exported tk2d sprite collection JSON')
    parser.add_argument('atlas', nargs='?', help='Exported tk2d atlas texture')
    parser.add_argument('--output', default=None, help='Output directory (default: spriteCollectionName from JSON)')
    parser.add_argument('--material-id', type=int, default=None, metavar='N',
                        help='Only extract sprites with materialId/texture N (default: all textures)')
    args = parser.parse_args()

    # show help if no input file specified
    if not args.collection:
        parser.print_help()
        exit(1)

    extract_sprites(args.collection, args.atlas, args.output, args.material_id)


if __name__ == '__main__':
    main()
