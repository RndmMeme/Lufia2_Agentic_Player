# Map Buffer Notes

This file tracks the live dungeon/town map buffer findings that are useful for
runtime decoding. These notes are intentionally conservative: they describe
observed behavior, not assumed engine internals.

## Current Working Model

- The blockage byte tells us only that movement failed in a direction.
- The live map buffer tells us what is actually on or near the tile.
- For navigation, the useful split is:
  - collision truth from Mesen WRAM `0x1272`
  - object/tile family truth from the live map buffer

So the runtime goal is not "find a magical collision table", but:

1. read the live map buffer
2. decode tile families and occupied variants
3. combine that with blocked-step data

## Secret Skills Cave Buffer

The older observations below came through the Snes9x/C# helper and therefore
included a helper-relative translation:

- x64/Snes9x range:
  - start/bottom anchor around `0xA36FA6`
  - top-left observed around `0xA3642B`
- relative WRAM slice:
  - `0x6421 .. 0x6FAB`

Direct Mesen WRAM access has now resolved that translation. For map ID `0x05`,
the confirmed formula is:

- `address = 0x4000 + live_x + live_y * 0x3A`
- registered dimensions: `58 x 64`
- examples:
  - live `(28,55)` -> `0x4C92`
  - live `(28,54)` -> `0x4C58`
  - live `(29,52)` -> `0x4BE5`

The old `0x6421` anchor and the direct Mesen `0x4000` base differ by `0x2421`.
This is a frontend/helper translation, not a change in the ROM or randomized
game logic.

Observed row behavior:

- horizontal progression inside a row behaves like `+1`
- vertical progression in the stable body of the buffer behaves like `-0x3A`

Example same-column northward stepping:

- `0xA36FA6`
- `0xA36EF8`
- `0xA36EBE`
- `0xA36E84`

This gives a practical row stride of:

- `0x3A` bytes per row

Important caveat:

- the active visible/useful window is not globally fixed across all dungeons
- the larger region appears to be reused by different map sizes/layouts
- do not assume every byte in `0x6421 .. 0x6FAB` is active room data in every map

## Tile Family Values

The safest working interpretation so far is:

- the tile family is the base value
- the occupied/touched form is often `base + 1`

This means occupancy is meaningful, but the base family still matters.

### Confirmed / Strongly Observed Families

- `0x00`
  - plain traversable floor family
- `0x01`
  - occupied/touched version of `0x00`

- `0x20`
  - alternate traversable floor family
- `0x21`
  - occupied/touched version of `0x20`

- `0x10`
  - structural/edge/corner family
- `0x11`
  - occupied/NPC/active variant of `0x10`

- `0x30`
  - second structural/edge/corner family
- `0x31`
  - occupied/NPC/active variant of `0x30`

- `0x02`
  - hole / gap family
- `0x03`
  - context-sensitive occupied/active variant of `0x02`
  - observed as an open chest in at least one case, so do not over-generalize it globally

- `0x06`
  - lever tile
- `0x07`
  - active/occupied lever-family variant

- `0x08`
  - obstacle family
  - observed on pillar, bush, pot, vines, movable block
- `0x09`
  - active/occupied obstacle-family variant

### Dynamic Examples

- enemy standing on a tile:
  - flips tile from base to `base + 1`
  - this appears to be entity-agnostic occupancy, not enemy-specific coding

- hole filled by lever:
  - `0x02 -> 0x00`

- bushes / vines:
  - `0x08` until cut
  - then `0x00`

- pillar / pot / movable block:
  - `0x08`

- floor switch:
  - base behaves like ordinary floor (`0x00`)
  - occupied becomes `0x01`

- stairs:
  - behave like ordinary floor
  - `0x00` base, `0x01` on contact

- locked door example:
  - one observed locked state used `0x10`
  - companion tile behind the door changed from `0x30` to `0x20` when unlocked/open

## Room-Specific Calibration Notes

These are useful legend/calibration hints, but they are not yet strong enough to
be treated as universal tile-family rules across every room.

### Secret Skills Cave

- Room 1
  - `0x10` is confirmed at the bottom-left corner
  - `0x30` is confirmed at the bottom-right corner
  - the right wall is very often `0x20`
  - much of the left wall is `0x00`
  - the top-most left walkable tile in room 1 can still be `0x30`, so `0x30` is
    not "always a wall"
  - example top row near the door:
    - `00 31 10 10 10 00 10 10 10 10 20`
    - first `00` = left wall
    - `31` = occupied tile just before the wall
    - middle `00` = walkable tile in front of the door
    - trailing `20` = right wall

- Room 2
  - slime appears roughly in the center of the room buffer
  - useful for enemy/occupancy validation

- Room 3
  - contains the bridge / lever setup
  - useful for validating `0x06` lever and `0x02 -> 0x00` bridge-hole change

- Room 4
  - contains a pushable pillar
  - useful for validating `0x08` obstacle-family behavior

Interpretation note:

- left/right/top/bottom circumference encoding is not yet clean enough to say
  "0x10 always means left/bottom" or "0x30 always means right/top" globally
- use these as room-verified hints, not universal rules

## Collision Byte Relationship

Blocked-step byte in direct Mesen WRAM:

- `0x1272`
  - `0xFF` = clear / no failed step
  - `0x00` = blocked north
  - `0x01` = blocked south
  - `0x02` = blocked west
  - `0x03` = blocked east

Important:

- this byte does not classify the object
- a wall, bush, pillar, pot, vine, hole edge, or similar blocker can all produce the same directional failure

So the correct high-level rule is:

- `0x1272` tells us "movement failed here"
- the map buffer tells us "what kind of tile/object is here"

## Known Limits

- active bounds vary by dungeon/location
- the live buffer seems to be part of a larger reused workspace
- until anchor/bounds logic is decoded per map, treat the full region as an inspectable source, not a perfect room rectangle

## Standalone Viewer

Helper script:

- [view_map_buffer.py](/d:/Projects/AI_Emu_Player/tools/view_map_buffer.py)

Current direct-Mesen behavior:

- map ID `0x05`: base `0x4000`, stride `0x3A`, dimensions `58 x 64`
- other maps remain unavailable until separately registered and proven

Usage:

```powershell
python tools/view_map_buffer.py
```

Live refresh:

```powershell
python tools/view_map_buffer.py --watch
```

Larger local window:

```powershell
python tools/view_map_buffer.py --watch --radius 4
```

The viewer is deliberately simple:

- it reads live WRAM through the active Mesen Lua bridge
- applies only an explicitly registered per-map address formula
- renders a bounded actor-centered tile-family window
- prints exact cardinal addresses, values, families and occupancy

It is meant as a reverse-engineering aid, not yet as the final runtime decoder.
