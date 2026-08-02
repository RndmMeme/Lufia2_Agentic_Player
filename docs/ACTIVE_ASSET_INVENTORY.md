# Active asset inventory

## Required for runtime state and control

- `agent/`: Mesen control loop, decoder, gates, navigation, perception, RAG
- `wram_discovery/mesen_bridge.py`: Python side of the live bridge
- `wram_discovery/mesen_bridge/mesen_wram_bridge.lua`: Mesen-side bridge
- `data/lufia2_wram_base_of_truth.json`: confirmed address and structure evidence
- `emulator/map_db.py`, `emulator/zone_db.py`: map and zone identity

## Required for planning and game completion

- `data/runtime_knowledge_manifest.json`: explicit retrieval/authority catalog
- `data/Walkthrough.txt`: puzzle fallback, not first-line navigation
- `data/locations_logic.json`: randomized access requirements
- `data/locations.json`, `data/town_POI_coords.txt`: overworld and town goals
- item, spell, IP, monster, shop, boss, capsule, and warp tables under `data/`
- Abyssonym/Terror Wave tables under `data/terrorwave_reference/`

## Required for dungeon navigation and vision

- all 29 directories under `emulator/maps/Dungeons/`
- manually curated marker JSON and compiled navigation JSON
- full-map images, grid overlays, and validation overlays
- `emulator/sprites/` as optional VLM references

## Generated runtime state

- `data/runs/`: bounded run journals, learned graphs, and LOOK frames
- `data/online_maps/`, `data/vision_observations/`: focused tool output
- Mesen bridge request/response files under `wram_discovery/mesen_bridge/shared/`

## Archived

The old Snes9x/C# helper, keyboard macros, PPO stack, Chroma state, discovery
captures, duplicate virtual environment, superseded checklists, and volatile
debug output are preserved under `legacy/`. They are not part of runtime or RAG.
