# Reverse Engineering Notes

This file captures verified memory findings that are useful for runtime logic.
Only record findings here when they are observed repeatedly and phrased conservatively.

## Mode Bytes

Observed on x64 Snes9x addresses:

- `0xA32CBB`
  - `0x00` on overworld / non-map contexts
  - `0x11` in towns and dungeons
  - Practical meaning: `map_context_flag`

- `0xA32CBD`
  - `0x01` during dungeon/town exploration
  - `0x04` while opening the tool menu via `Select`
  - `0x00` during battle and after the tool menu settles into non-exploration UI
  - Practical meaning: `exploration_mode_flag`

- `0xA32CBE`
  - `0x01` during battle flow
  - Returns to `0x00` once results are cleared and exploration resumes
  - Practical meaning: `battle_mode_flag`

Useful composite interpretation:

- Exploration mode:
  - `0xA32CBB = 0x11`
  - `0xA32CBD = 0x01`
  - `0xA32CBE = 0x00`

- Battle mode:
  - `0xA32CBB = 0x11`
  - `0xA32CBD = 0x00`
  - `0xA32CBE = 0x01`

This is more trustworthy than the old fake `0xA305C6` battle flag.

## Collision / Failed-Step Byte

- `0xA33586` (`0x3586` relative WRAM)
  - `0xFF` = free movement / no blocked step
  - `0x00` = blocked north
  - `0x01` = blocked south
  - `0x02` = blocked west
  - `0x03` = blocked east

Important caveat:

- This is a blocked-step result, not a wall classifier.
- It reports that movement failed in a direction.
- The reason can be:
  - wall
  - movable object
  - bush / vine / pot / pillar
  - hole / cliff / non-walkable puzzle tile

So runtime code should store this as a blocked edge or unknown blocker, not blindly as a wall.

## Tool Menu / Tool Trigger Bytes

Observed while opening the `Select` tool menu and using tools.

### Tool Focus Byte

- `0xA32D1A`
  - Holds the leading byte of the currently focused tool while the tool menu is open.

Observed values:

- `A7` = Hook (`A703`)
- `A8` = Bomb (`A803`)
- `A9` = Arrow (`A903`)
- `AA` = Fire Arrow (`AA03`)
- `AB` = Hammer (`AB03`)

This is likely the cleanest byte for tool selection/focus detection.

### Tool Classification / Companion Bytes

- `0xA32D1D`
- `0xA32D1E`

Observed together with `0xA32D1A`:

- Hammer: `19 / F8`
- Hook: `E5 / F7`
- Bomb: `F2 / F7`
- Arrow: `FF / F7`
- Fire Arrow: `0C / F8`

Meaning is not fully decoded yet.
Treat them as companion classification/state bytes for the selected tool, not as stable IDs by themselves.

### Tool Use / Animation Byte

- `0xA32CBC`
  - Usually `0x00`
  - Changes while a tool is actively being used / visible

Observed behavior:

- Arrow:
  - `0x6F`
  - then briefly `0x4E`
  - then back to `0x00`

- Fire Arrow:
  - `0x6F`
  - then briefly `0x4E`
  - then back to `0x00`

- Hook:
  - `0x7E`
  - then back to `0x00`

- Hammer:
  - `0x7F`
  - then back to `0x00`

- Bomb:
  - `0x77` while visible
  - may flicker to `0x37`
  - becomes `0x7F` on explosion
  - then returns to `0x00`

Interpretation:

- `0xA32CBC` looks useful for detecting active tool execution/animation state.
- It is not a persistent “which tool is selected” byte; `0xA32D1A` is better for that.

## Direction History FIFO

- `0xA32CB5 .. 0xA32CB9`

Observed behavior:

- Stores recent movement directions in a left-to-right shifting series.
- Example movement direction values:
  - `0x00` = north
  - `0x01` = south
  - `0x02` = west
  - `0x03` = east

Example pattern:

```text
03 00 00 00 00
00 03 00 00 00
01 00 03 00 00
02 01 00 03 00
02 02 01 00 03
02 02 02 01 00
```

Interpretation:

- This is not the live collision truth.
- This is not a reliable wall-contact byte.
- It behaves more like a short direction-history FIFO or movement trace buffer.

Practical advice:

- Do not use `0xA32CB5..0xA32CB9` for blocked-edge detection.
- Keep using `0xA33586` for failed-step direction.

## Dungeon Coordinate Hints

Observed dungeon-mode bytes:

- `0xA32368`
- `0xA3236E`
- `0xA3236B`
- `0xA3236F`

Current interpretation:

- `0xA32368` and `0xA3236E` step by `0x10` per tile in dungeon mode.
- `0xA3236B` changes when passing `0xF0` on the X axis.
- `0xA3236F` changes when passing `0xF0` / wrapping on the Y axis.

Likely model:

- `0xA32368` = local X within chunk/page
- `0xA3236B` = X chunk companion
- `0xA3236E` = local Y within chunk/page
- `0xA3236F` = Y chunk companion

Important caveat:

- At least `0xA32368` / `0xA3236E` are reused by battle and UI logic.
- Do not treat them as universal coordinates outside dungeon movement context.

# Live Map Buffer Notes

Observed x64 Snes9x WRAM-backed buffer behavior:

- Secret Skills Cave appears to render continuously in WRAM from:
  - bottom: `0xA36FA6`
  - top-left: `0xA3642B`
- Relative WRAM range:
  - `0x642B .. 0x6FA6`

The active map buffer is not assumed to be a universal fixed-size source for every dungeon.
Different dungeons may use shorter or longer active spans inside the broader region.

## Observed Row Behavior

- Horizontal neighbors are adjacent bytes.
- For the Secret Skills Cave buffer, the practical row stride appears to be `0x3A` in the stable body of the map.
- Example vertical stepping in room 1:
  - `0xA36EF8 -> 0xA36EBE -> 0xA36E84`
  - delta `-0x3A`

There are some entrance/transition special cases, so the stride is useful for decoding, but should still be treated as an observed working assumption rather than a universal theorem.

## Tile Family Notes

Important:

- Do **not** assume `0x00` means void.
- In Lufia II, `0x00` is often an ordinary traversable tile family.
- The low bit appears to act as an occupancy / contact bit:
  - base tile -> occupied/touched tile is often `base + 1`

This means:

- `0x00 -> 0x01`
- `0x20 -> 0x21`
- `0x10 -> 0x11`
- `0x30 -> 0x31`

The upper bits encode tile family/state, not pure walkability by themselves.

## Observed Tile Values

Current observed working catalog:

- `0x00`
  - plain traversable tile family
  - stairs and ordinary floor may use this family

- `0x01`
  - occupied / touched variant of `0x00`
  - also used when an enemy occupies a tile of the `0x00` family

- `0x20`
  - alternate traversable tile family

- `0x21`
  - occupied / touched variant of `0x20`

- `0x10`
  - structural / edge / corner family

- `0x11`
  - occupied / touched variant of `0x10`

- `0x30`
  - another structural / edge / corner family

- `0x31`
  - occupied / touched variant of `0x30`
  - observed with NPC occupation

- `0x02`
  - hole / gap family

- `0x03`
  - context-sensitive `0x02`-family variant
  - observed as open chest state in at least one case
  - should not yet be treated as globally "open chest" without context

- `0x06`
  - lever tile

- `0x07`
  - occupied / active variant of lever-family tile

- `0x08`
  - obstacle family
  - observed for pillar, bush, pot, vines, movable blocks

- `0x09`
  - occupied / active variant of obstacle-family tile

## Dynamic State Examples

- Hole filled by lever:
  - `0x02 -> 0x00`

- Locked door:
  - observed as `0x10`

- Unlocked / open door companion tile:
  - observed changing from `0x30 -> 0x20`

- Bushes / vines:
  - `0x08` until cut
  - then `0x00`

## Practical Guidance

- Use `0xA33586` (`0x3586` relative) to know **that** movement failed.
- Use the live map buffer to reason about **what** is there.
- Do not try to derive blocker type from the collision byte alone.
