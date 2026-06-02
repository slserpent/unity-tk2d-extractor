"""
batch_extract.py
Wrapper script to batch-extract sprites from all Unity tk2d collections in an Asset Studio export directory.
Requires Asset Studio to be set to export with assets grouped by type and named including the pathID.

Scans MonoBehaviour/ for sprite collection JSONs and Texture2D/ for atlas textures,
matches them by the path ID embedded in Asset Studio filenames, and calls extract_tk2d_sprites.py
for each matched pair. Since Asset Studio can mix up textures with the same ID but different
asset files, collections whose texture path ID is shared by more than one collection are
skipped with a report, so they can be resolved manually.

Requirements:
    Python 3.8+
    pip install Pillow  (used by extract_tk2d_sprites.py)

Usage:
    python batch_extract.py <export_dir> [options]

Arguments:
    export_dir          Asset Studio export directory (must contain MonoBehaviour/ and Texture2D/ subdirs)
    --texture-ext EXT   File extension of exported atlas textures to match (default: png)
    --output DIR        Root output directory; each collection gets a subdirectory here (default: working directory)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EXTRACT_SCRIPT = Path(__file__).parent / 'extract_tk2d_sprites.py'
ILLEGAL_NAME_CHARS = re.compile(r'[/\\:*?"<>|]')
# Asset Studio appends @<pathID> to exported filenames
PATH_ID_RE = re.compile(r'@(\d+)\.')


def sanitize(name):
    return ILLEGAL_NAME_CHARS.sub('_', name)


def build_texture_map(texture_dir, ext):
    """Return {path_id: Path} for all texture files matching *@<id>.<ext>."""
    texture_map = {}
    for tex_file in sorted(texture_dir.glob(f'*.{ext}')):
        m = PATH_ID_RE.search(tex_file.name)
        if m:
            texture_map[int(m.group(1))] = tex_file
    return texture_map


def main():
    parser = argparse.ArgumentParser(
        description='Batch-extract sprites from an Asset Studio export directory.')
    parser.add_argument('export_dir', nargs='?',
                        help='Asset Studio export directory containing MonoBehaviour/ and Texture2D/')
    parser.add_argument('--texture-ext', default='png', metavar='EXT',
                        help='Texture file extension to look for (default: png)')
    parser.add_argument('--output', default=None, metavar='DIR',
                        help='Root output directory (default: current working directory)')
    args = parser.parse_args()

    # show help if no input directory specified
    if not args.export_dir:
        parser.print_help()
        exit(1)

    # locate the expected Asset Studio export subdirectories
    export_dir = Path(args.export_dir)
    mono_dir = export_dir / 'MonoBehaviour'
    texture_dir = export_dir / 'Texture2D'

    if not mono_dir.is_dir():
        print(f"Error: MonoBehaviour directory not found: {mono_dir}", file=sys.stderr)
        sys.exit(1)
    if not texture_dir.is_dir():
        print(f"Error: Texture2D directory not found: {texture_dir}", file=sys.stderr)
        sys.exit(1)

    # index all available atlas textures by path ID
    texture_map = build_texture_map(texture_dir, args.texture_ext)

    # collect all collection JSONs to process
    collections = sorted(mono_dir.glob('*.json'))

    if not collections:
        print(f"No JSON files found in {mono_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(collections)} JSON file(s), {len(texture_map)} texture(s)\n")

    # --- Pre-scan: parse all collections, find path IDs referenced by more than one ---
    parsed = {}      # coll_path -> collection dict
    pid_refs = {}    # path_id -> [coll_path, ...]
    errors = 0

    for coll_path in collections:
        # load and validate each JSON as a sprite collection
        try:
            with open(coll_path, encoding='utf-8') as f:
                collection = json.load(f)
        except Exception as e:
            print(f"Error: {coll_path.name}: failed to read: {e}", file=sys.stderr)
            errors += 1
            continue

        if 'spriteDefinitions' not in collection:
            print(f"Skipping {coll_path.name}: not a tk2dSpriteCollectionData", file=sys.stderr)
            continue

        # record which collections reference each texture path ID
        parsed[coll_path] = collection
        for ref in collection.get('textures', []):
            pid = ref.get('m_PathID', 0)
            if pid > 0:
                pid_refs.setdefault(int(pid), []).append(coll_path)

    # path IDs are bundle-local, so the same ID in two collections may mean different textures
    ambiguous_ids = {pid for pid, colls in pid_refs.items() if len(colls) > 1}

    # --- Planning pass: build job list and skip list ---
    jobs = []     # list of (label, cmd, coll_filename)
    skipped = []  # list of (coll_filename, path_id) for ambiguous pairs

    for coll_path, collection in parsed.items():
        coll_name = sanitize(collection.get('spriteCollectionName', coll_path.stem))
        tex_refs = collection.get('textures', [])

        if not tex_refs:
            print(f"Error: {coll_path.name}: textures array is empty", file=sys.stderr)
            errors += 1
            continue

        # match each texture reference to a file, skipping ambiguous or missing IDs
        matched = []
        for n, ref in enumerate(tex_refs):
            path_id = ref.get('m_PathID', 0)
            if path_id <= 0:
                continue  # null Unity reference
            path_id = int(path_id)
            if path_id in ambiguous_ids:
                skipped.append((coll_path.name, path_id))
            elif path_id not in texture_map:
                print(f"Error: {coll_path.name}: no {args.texture_ext} file found for "
                      f"textures[{n}].m_PathID={path_id}", file=sys.stderr)
                errors += 1
            else:
                matched.append((n, texture_map[path_id]))

        # multi-atlas collections get indexed output dirs and per-material filtering
        multi = len(matched) > 1
        for n, atlas_path in matched:
            out_name = f'{coll_name}_{n}' if multi else coll_name
            out_path = str(Path(args.output) / out_name) if args.output else out_name

            label = f"{coll_path.name} + {atlas_path.name}"
            if multi:
                label += f" (material {n})"

            cmd = [sys.executable, str(EXTRACT_SCRIPT), str(coll_path), str(atlas_path),
                   '--output', out_path]
            if multi:
                cmd += ['--material-id', str(n)]

            jobs.append((label, cmd, coll_path.name))

    # --- Print skip report before any extraction output ---
    if ambiguous_ids:
        print("Skipped (ambiguous texture path ID — referenced by multiple collections):")
        for pid in sorted(ambiguous_ids):
            print(f"  path ID {pid}:")
            for coll_path in pid_refs[pid]:
                coll_name = parsed[coll_path].get('spriteCollectionName', '')
                print(f"    {coll_path.name}  ({coll_name})")
        print()

    # --- Execution pass ---
    for label, cmd, coll_filename in jobs:
        print(f"--- {label}")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"Error: extract_sprites.py exited with code {result.returncode} "
                  f"for {coll_filename}", file=sys.stderr)
            errors += 1
        print()

    if errors:
        print(f"{errors} error(s) occurred.", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
