# Legacy archive

This directory contains preserved, inactive material from the former Snes9x,
C# helper, keyboard-macro, PPO, and WRAM-discovery workflows.

Nothing under `legacy/` is imported or required by the active Mesen runtime.
Files are moved here rather than deleted so prior experiments, validation
evidence, and implementation details remain recoverable.

## Archive groups

- `snes9x_runtime/`: former top-level orchestrator and launch/config files
- `agent_snes9x/`: old LLM prompt stack, RL environment, and keyboard macros
- `emulator_snes9x/`: C# process-memory helper and Snes9x-specific readers
- `wram_research/`: one-off discovery sessions, dumps, and audit scripts
- `tools_snes9x/`: helper-bound diagnostic and shadow-mapping tools
- `generated/`: volatile debug output, old briefings, and superseded maps
- `environments/`: inactive local Python/build environments

The authoritative runtime facts remain outside this archive in `data/`,
`docs/`, `emulator/maps/Dungeons/`, and the Mesen bridge.
