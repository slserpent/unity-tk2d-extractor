# tk2d Sprite Extractor

Extracts individual sprites from Unity games that use the 2D Toolkit (tk2d) sprite system. tk2d can either packs many small sprites into a single large texture, or a single texture into an optimized sprite (it might look like lots of jumbled up tiles). Is only confirmed to be working with the game HuniePop at the moment, which uses tk2d format version 3. Other games and version may or may not work. Fork or add issues if you need to.

Assets can be exported using [Asset Studio](https://github.com/aelurum/AssetStudio), but other Unity asset extractors will probably work as well. You'll want to extract the Texture2D atlas image files and the companion MonoBehaviour `tk2dSpriteCollectionData` JSON files that describe how to unpack the sprites.

`extract_tk2d_sprites.py` can be used independently of `batch_extract.py`, the latter is just a wrapper to simplify extracting from many sprite collections if they were created using Asset Studio.

---

## Requirements

- Python 3.8+
- Pillow — `pip install Pillow`

---

## Asset Studio Setup

If using Asset Studio, before exporting, configure it so the scripts can match collections to atlases:

1. **Options → Export → Group exported assets by: type** — this puts MonoBehaviours and Texture2Ds into separate subdirectories.
2. **Options → Export → Filename format: asset name @pathID** — this embeds the path ID (e.g. `@77`) in each filename, which  batch script uses to match a collection JSON to its atlas texture.
3. Make sure **Texture2D is being converted to a supported image type** like PNG.

Export the assets you need. The export directory should contain at minimum:
- `MonoBehaviour/` — sprite collection JSONs (`AssetName @<id>.json`)
- `Texture2D/` — atlas textures (`AssetName @<id>.png`)

---

## Scripts

### `extract_tk2d_sprites.py` — Extract sprites from a single collection

Reads one `tk2dSpriteCollectionData` JSON and its matching atlas texture, and outputs one PNG per sprite definition.

**Usage:**
```
python extract_tk2d_sprites.py <collection.json> <atlas> [options]
```

**Arguments:**

| Argument | Description |
|---|---|
| `collection.json` | Exported `tk2dSpriteCollectionData` JSON |
| `atlas` | Exported atlas texture |
| `--output DIR` | Output directory for extracted PNGs (default: `spriteCollectionName` from JSON) |
| `--material-id N` | Only extract sprites with `materialId` N; for multi-atlas collections (default: all) |

**Example:**
```
python extract_tk2d_sprites.py "tk2dSpriteCollectionData @9395.json" "atlas0 @77.png" --output ./sprites
```

---

### `batch_extract.py` — Batch-extract an entire export directory

Scans an Asset Studio export directory, matches every collection JSON to its atlas texture by path ID, and calls `extract_tk2d_sprites.py` for each pair. Each collection is extracted into its own subdirectory named after `spriteCollectionName`.

If two collection JSONs reference the same texture path ID, both are skipped and reported — path IDs are bundle-local, so the same numeric ID in two different asset files refers to different textures, and there is no way to auto-resolve the conflict. The report lists the filename and `spriteCollectionName` for each affected collection so they can be manually matched and processed with `extract_tk2d_sprites.py`.

**Usage:**
```
python batch_extract.py <export_dir> [options]
```

**Arguments:**

| Argument | Description |
|---|---|
| `export_dir` | Asset Studio export directory (must contain `MonoBehaviour/` and `Texture2D/` subdirs) |
| `--texture-ext EXT` | File extension of exported atlas textures (default: `png`) |
| `--output DIR` | Root output directory; each collection gets a subdirectory here (default: working directory) |

**Example:**
```
python batch_extract.py ./AssetStudioExport --output ./sprites
```
