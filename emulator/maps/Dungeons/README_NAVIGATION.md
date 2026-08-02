# Offline dungeon-map curation

`navigation_index.csv` and `NAVIGATION_INDEX.md` list every generated dungeon
pack. Each of the 29 dungeon folders contains:

- `navigation/grid_coordinates.png`
- `navigation/navigation_preview.png`
- `navigation/navigation_map.json`
- `navigation/navigation_map.txt`
- `navigation/object_map.txt`
- `annotations.json`

The source images are guide sheets and may contain letters, item labels,
credits or decorative overview art. Those printed guide elements are not game
tiles and should not be annotated as terrain.

## Coordinates

The displayed coordinate always identifies the image tile:

- column `A` is image tile X 0;
- row `1` is image tile Y 0;
- `AC55` means image X 28, image Y 54.

Only Secret Skills Cave currently has a live-proven direct mapping between
image tiles and WRAM actor tile coordinates. All other maps are marked
`unverified` until one visible live position registers their image offset.
Offline annotations remain valid because they stay in image coordinates.

## Curation list

Copy `curation_list_template.csv`, replace its example row, and add one row per
object or exceptional tile. Recommended values:

- `blocked`: permanent wall or obstacle;
- `conditional`: bush, bombable wall, secret passage, movable block or other
  state-dependent tile;
- `confirmed_walkable`: known floor;
- `unknown`: explicitly unresolved.

Typical object names are `bush`, `bombable_wall`, `secret_passage`, `stairs`,
`door`, `switch`, `pillar`, `movable_block`, `chest`, `monster_spawn`, and
`transition`.

## Render space and collision space

The 16x16 grid is a navigation lattice anchored at the actor's feet. It is
not a visual object segmentation. Maxim is rendered in a 2x4-tile (32x64
pixel) rectangle, and his head may overlap a wall while collision still
occurs at foot height. Doors likewise span several visible tiles.

`navigation_map.json` therefore contains separate `object_rules` and
`semantic_objects`. `object_map.txt` is a compact object-only layer and does
not replace the traversal map.

Door rules:

- the pedestal arrow is the front anchor;
- the lighter gap in the wall is the back face of that same local doorway;
- doors are bidirectional north/south transitions only;
- a door front is never paired with a remote door back.

Stair rules:

- one stair endpoint occupies one 16x16 tile;
- stairs are enterable from all four sides unless another obstacle blocks an
  approach;
- internal stairs have one paired endpoint; a labelled dungeon entrance or
  exit may have its counterpart outside the guide sheet;
- both endpoints have the same `L` or `R` handedness.

Monster sprites are dynamic occupancy, separate from the underlying terrain.
A mandatory monster can mark its occupied cells `conditional` with `defeat`
as the required action. A moving optional monster can instead use
`move_away_or_defeat`.

NPC markers use `N` and are dynamic occupancy as well. Their underlying floor
is stored separately; `talk_or_move_around` is the default interaction.

## Point-and-click curation editor

For fast visual correction, open the local editor from the workspace root:

```powershell
python tools\dungeon_curation_editor.py --dungeon Cave_to_Sundletan
```

The editor keeps the 16x16 navigation grid as a reference but places manual
markers as 16x16 object boxes by default. Marker position and marker size are
independent:

- `1 px` snap allows exact visual centering;
- `8 px` snap follows the underlying SNES half-tile structure;
- `16 px` snap follows the navigation reference grid;
- marker sizes are 16x16, 32x32 or 32x64.

Legacy process annotations start hidden. Use `Import visible legacy boxes as
editable` to convert them into draggable markers, or leave them hidden and
curate from the clean source map. Left click places, dragging moves, right-drag
pans, the mouse wheel zooms, `Ctrl+Z`/`Ctrl+Y` undo and redo, and `Delete`
removes the selected marker. Arrow keys nudge selected markers by one pixel;
Shift+arrow moves eight and Ctrl+arrow moves sixteen pixels.

Manual data is saved as `curation_markers.json` inside the selected dungeon
folder. `Export preview` creates
`navigation/manual_curation_preview.png`, combining the original map, the
16-pixel reference grid and the manual markers.

## Compile and validate all manual maps

Compile the exact pixel markers into a 16x16 reference-cell layer and generate
QA reports:

```powershell
python tools\compile_dungeon_curation.py
```

The compiler keeps every exact pixel box and derives an anchor plus primary and
touched reference cells. Per dungeon it writes:

- `navigation/compiled_curation.json`
- `navigation/compiled_curation_map.txt`
- `navigation/curation_validation.json`
- `navigation/curation_validation_overlay.png`

Global reports are written to `curation_validation.json`,
`curation_validation.csv`, and `CURATION_VALIDATION.md` in the Dungeons folder.
Allowed cross-layer combinations such as a bush hiding a switch or a puzzle in
lava are not treated as duplicates.

Tight half-tile transitions can be resolved without moving their exact marker
boxes. A dungeon-local `curation_navigation_overrides.json` records the
user-confirmed result for the ambiguous 16x16 reference cell. Supported states
include `blocked`, `conditional`, `confirmed_walkable`, and `partial`; partial
cells retain exact pixel geometry and may include a `walkable_fraction`.

`CURATION_REVIEW.md` summarizes unresolved geometry candidates, while
`curation_review.csv` contains their marker-level list. Redundant overlap of
equally blocked hard terrain is accepted as harmless coverage. Conditional
markers without an action are intentionally tracked in
`curation_learning_backlog.csv`: the player explores first, consults the
walkthrough only when stuck, and can persist the learned solution afterward.

Validate a completed list without changing annotations:

```powershell
python tools\import_dungeon_curation.py my_curation.csv --dry-run
```

Import it and rebuild all generated maps:

```powershell
python tools\import_dungeon_curation.py my_curation.csv
python tools\build_all_dungeon_navigation_maps.py
```
