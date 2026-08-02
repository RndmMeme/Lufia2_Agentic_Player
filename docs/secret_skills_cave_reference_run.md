# Secret Skills Cave Reference Run

This document separates reusable engine lessons from facts that are valid only
for the Secret Skills Cave. It is based on the completed live Mesen reference
run, not on a claimed universal transform from the stitched screenshot map.

## Globally reusable engine lessons

- Live actor coordinates and collision contact use the actor's feet as anchor.
- A failed step plus WRAM `0x1272` proves `blocked_now` in one direction. It does
  not prove a permanent wall or a blocked reverse edge.
- Exploration can use bounded direction holds. Menus require short human-sized
  presses followed by state verification.
- A locked door, actor, bush, movable object, elevation boundary and wall can all
  prevent movement. Structural classification needs additional evidence.
- Room Reset is `Select`, `Up`, then bounded `A` confirmation. During reload the
  field/battle bytes can briefly oscillate; accept it only after consecutive
  `exploration=01, battle=00` observations.
- The LLM chooses navigation and puzzle actions. The mapper records evidence and
  progress but must not silently become the route planner.
- Visual inspection is on demand (`look` or `look_map`); routine decisions use
  compact WRAM, room state, feedback and navigation memory.

## Secret Skills Cave only

- Map ID is `0x05`.
- Its confirmed Mesen tile-buffer formula is
  `0x4000 + live_x + live_y * 0x3A`, registered as `58 x 64`.
- The older Snes9x/C# observation at `0x6421` contained a helper-relative
  translation of `0x2421`; it was not a different ROM map layout.
- All small transit rooms in this cave share the same geometry: two live tiles
  left and two live tiles right of the aligned arrival column. Door traversal is
  north-south.
- A red wall object can be a torch. It is not automatically a door, switch or
  NPC.
- Room 3 requires shooting the distant switch, crossing the completed bridge and
  taking the west door. The left transit corridor is not visible before entry.
- Room 4 requires pushing the pillar onto its switch. Feet/base alignment is the
  contact reference.
- Room 5 and room 6 contain elevation. Arrow ledges descend; ladders restore the
  upper route. In room 6 the ladder begins at curated `AO12` / live `(31,11)`.
- Both room-6 encounters are mandatory; green first is the shorter ordering.
- In room 7, cut only the shortest bush path. The switch under a bush is at live
  `(50,12)` on the pale central floor patch. An already defeated boss is shown by
  the crown.
- Room 8 uses two vases and two switches, then returns through the loop to room 3.
- Completion means visiting all eight resolved rooms and returning within radius
  one of live start `(28,55)`, not merely re-entering room 1.

## Tile-buffer policy

The cave buffer is useful as a compact local sensor and as an internal diff:

- emit only a small actor-centered window to the model;
- record non-actor changes after actions;
- combine family changes with vision, room semantics and `blocked_now`;
- never promote a cave tile-family meaning to a global rule without evidence
  from another registered map.

Canonical machine-readable sources:

- `data/navigation_semantics/global_engine.json`
- `data/navigation_semantics/secret_skills_cave.json`
- `data/navigation_objectives/secret_skills_cave_room_sweep.json`
