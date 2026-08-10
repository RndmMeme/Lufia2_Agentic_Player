# Lufia II Mesen Agent

Mesen-only autonomous player for a randomized **Lufia II: Rise of the
Sinistrals** ROM. The randomizer preserves the memory layout.

The active runtime is deliberately bounded:

- coherent 128-KiB WRAM snapshots from Mesen Lua;
- frame-bounded controller input, never OS-wide keyboard injection;
- LLM-owned navigation plus WRAM-gated, LLM-owned battle tactics;
- schema-gated local LLM decisions only when reasoning is useful;
- on-demand VLM observations for doors, objects, puzzles, and recovery;
- curated dungeon maps, ROM tables, walkthrough snippets, and WRAM truth;
- action/time limits plus a resumable JSONL journal for every run.

The former Snes9x/C# helper/PPO stack is preserved under [legacy](./legacy/README.md)
and is not imported by the active runtime.

## Start

1. Load `wram_discovery\mesen_bridge\mesen_wram_bridge.lua` in Mesen.
2. Enable Mesen's **Allow access to I/O and OS functions** option and run the script.
3. Verify the bridge:

```powershell
python wram_discovery\mesen_bridge.py doctor
```

4. Observe without sending input:

```powershell
python run_agent.py
```

5. Run a bounded deterministic session:

```powershell
python run_agent.py --execute --max-actions 40 --max-minutes 3
```

The local model is disabled by default. The runtime uses a project-local Ollama
server on port `11435`, with llama.cpp and KoboldCpp as fallbacks. Planning,
vision, deliberate recovery and battle use one resident multimodal model:

- the project server is launched by `start_project_ollama_cuda.ps1`;
- Qwen3-VL 4B is the current single-resident model for every role;
- it disables Vulkan only for that child process and uses the RTX through CUDA;
- the user's global Ollama on port `11434` remains unchanged;
- LOOK/LOOK_MAP are still on demand, so routine turns do not resend images.

Start the project-local server and enable model calls with:

```powershell
.\start_project_ollama_cuda.ps1
python run_agent.py --execute --enable-llm --max-actions 100
```

Battle input has a separate feature gate. Enable it only together with the
model; a run launched in the middle of an unknown battle UI state remains
fail-closed:

```powershell
python run_agent.py --execute --enable-llm --enable-battle --max-actions 100
```

For a deliberately supervised resume when Mesen is already waiting on a known
character action cross:

```powershell
python run_agent.py --execute --enable-llm --enable-battle `
  --resume-battle-stage action_cross --resume-battle-actor 0
```

Optional run-over-run learning is disabled by default. Shadow mode only
collects evidence-backed proposals; gated mode additionally promotes proposals
repeated in independent runs, measures them as canaries, and rolls them back on
poor outcomes:

```powershell
python run_agent.py --execute --enable-llm --enable-harness-refiner
python run_agent.py --execute --enable-llm --enable-harness-gated
python tools\harness_control.py status
```

See [docs/continual_harness.md](./docs/continual_harness.md) for lifecycle,
isolated A/B stores, runtime subagents, promotion and rollback.

Cline can help develop the workspace, but it is not part of the autonomous
player's runtime or authority chain.

PowerShell wrapper:

```powershell
.\start_mesen_agent.ps1 -Execute -EnableLlm -EnableBattle -MaxActions 40
```

## Active architecture

- [run_agent.py](./run_agent.py): bounded entry point
- [agent/orchestrator.py](./agent/orchestrator.py): control loop and journal
- [agent/game_state.py](./agent/game_state.py): confirmed WRAM decoder
- [agent/mesen_controller.py](./agent/mesen_controller.py): verified Mesen input
- [agent/intent.py](./agent/intent.py): model-action schema and state gate
- [agent/model_client.py](./agent/model_client.py): local text/VLM client
- [agent/adaptation](./agent/adaptation): continual-harness refinement, global state and rollback
- [agent/navigation](./agent/navigation): directed online graph and POIs
- [agent/perception](./agent/perception): sparse visual keyframes
- [agent/knowledge.py](./agent/knowledge.py): deterministic lightweight RAG
- [docs/MESEN_ARCHITECTURE.md](./docs/MESEN_ARCHITECTURE.md): authority and safety design

## Useful focused tools

```powershell
# Ask for a synchronized visual/WRAM bundle
python tools\mesen_look.py --question "Is this a wall, locked door, or movable object?"

# Compare installed local models against the real intent and LOOK schemas
python tools\benchmark_local_models.py

# Curate or rebuild dungeon maps
python tools\dungeon_curation_editor.py --dungeon Secret_Skills_Cave
python tools\compile_dungeon_curation.py

# Run the older focused room-sweep probe
python tools\run_mesen_room_sweep.py --execute --max-actions 40 --visual-keyframes
```

## Runtime facts

- Expected ROM SHA-1: `1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0`
- Required Lua bridge protocol: `2` (shown by `mesen_bridge.py doctor`)
- Mesen WRAM: `7E:0000-7F:FFFF` / 131072 bytes
- A failed movement means directed `blocked_now`; it is not automatically a wall.
- Visual appearance adds semantics but never overrides contradictory WRAM movement.
- Menus use 2-frame taps followed by neutral/settle time. Exploration directions
  are held for a short humanoid walking interval and then WRAM-observed. The
  cursorless battle action cross uses the game's required direction lead followed
  by direction+A; battle results hold A continuously until battle mode ends.
- The active config is [runtime_config.json](./runtime_config.json).
