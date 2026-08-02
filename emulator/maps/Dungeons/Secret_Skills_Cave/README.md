# Secret Skills Cave navigation map

The full dungeon screenshot in this directory is the canonical visual source.
The earlier room-splitting experiment is preserved under
`_archive/rooms_pre_navigation_20260726`.

Generated navigation files are under `navigation/`:

- `grid_coordinates.png`: enlarged source image with a 16x16-pixel tile grid,
  column letters and row numbers, plus a label inside every tile.
- `navigation_map.json`: machine-readable 75x64 tile map.
- `navigation_map.txt`: compact ASCII view (`# . ? o S B`).
- `object_map.txt`: compact object-only view (`D T H b C M ...`).
- `navigation_preview.png`: visual-state overlay for quality control.

Coordinates use zero-based WRAM tile positions but human-readable labels:

- WRAM X 0 is column `A`; X 25 is `Z`; X 26 is `AA`.
- WRAM Y 0 is displayed as row `1`.
- The live registration point X 28, Y 54 is therefore `AC55`.

## Annotation semantics

Edit `annotations.json` and regenerate the map. Examples:

```json
"BK7": {
  "traversal": "blocked",
  "object": "bush",
  "notes": "Cuttable with sword."
},
"AC54": {
  "traversal": "conditional",
  "object": "bombable_wall"
},
"M8": {
  "traversal": "conditional",
  "object": "secret_passage"
}
```

Black borders are blocked by default. `secret_passage` and `bombable_wall`
are explicit conditional exceptions; a navigator must not use them until the
required interaction and a successful live movement confirm the edge.

The grid describes the actor's feet anchor, not the visible 32x64-pixel
sprite rectangle. Doors are local bidirectional north/south passages; their
front arrow and brighter rear wall gap are two faces of the same passage.
Stairs occupy one 16x16 tile, may be entered from all four sides, and pair
only with a stair of the same L/R handedness.

Regenerate from the workspace root:

```powershell
python tools\build_dungeon_navigation_map.py `
  "emulator\maps\Dungeons\Secret_Skills_Cave\SNES - Lufia 2_ Rise of the Sinistrals - Dungeon - Secret_Skills_Cave.png" `
  --annotations "emulator\maps\Dungeons\Secret_Skills_Cave\annotations.json" `
  --runtime-alignment direct
```
