# Local model qualification

The autonomous player uses one resident multimodal model for both structured
state decisions and on-demand screenshots. A model is not allowed to control
Mesen merely because it starts successfully or produces valid JSON.

## Current live candidate

- Model: `Qwen3-VL-4B-Spatial-Analysisv2.Q8_0.gguf`
- Backend: resident llama.cpp server on the RTX
- Best observed live run: Run 29, Room 3, two tiles before the left door
- Important: Run 29 did not enter Room 4
- Promotion status: best live candidate, but the full cave must still be
  completed twice before expanding scope

The earlier Arc/Vulkan path exceeded 30 seconds per live decision. Improving
Mesen bridge transport may remove seconds of idle time, but is not evidence
that a larger model will be faster or navigate better. The 4B spatial model
therefore remains primary until a controlled test demonstrates a model-capacity
failure rather than a context, room-resolution, or control failure.

## Historical offline-qualified candidate

- Model: official `Qwen/Qwen3-VL-8B-Instruct-GGUF`
- Language quant: `Qwen3VL-8B-Instruct-Q4_K_M.gguf` (5.03 GB)
- Vision projector: `mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf` (752 MB)
- Backend: project-local llama.cpp Vulkan build, `Vulkan0`
- Runtime context: 12288 tokens, one server slot, Q8 KV cache
- Vision input: at least 1024 image tokens for Qwen grounding
- Reasoning mode: off; the harness supplies bounded evidence and actions

The model and projector come from the same official repository and must not be
mixed with a projector from another conversion.

Official SHA-256 values:

- Q4_K_M model: `67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2`
- Q8_0 projector: `c6ba85508d82f42590e6eb77d5340369ab6fecf107a7561d809523d8aa5f3bfd`

## Offline contract

`data/benchmarks/lufia_agent_contract_v1.json` contains machine-checkable cases
derived from the completed Mesen Secret Skills Cave reference run:

- incomplete and completed Room-3 bridge states;
- replacing a wrong selected dungeon tool;
- dialog interaction;
- bridge decisions with actual before/after screenshots;
- ladder and elevation grounding;
- the hidden bush switch;
- vase and floor-switch grounding.

Run it without connecting to Mesen:

```powershell
python tools\benchmark_lufia_agent.py --repeats 2
```

For a text-only baseline:

```powershell
python tools\benchmark_lufia_agent.py --skip-vision
```

Qualification requires at least 90 percent across all cases. Before emulator
control, failures must also be reviewed semantically: a model must not pass by
guessing an accepted action for a contradictory rationale.

The accepted qualification report is
`data/benchmarks/qwen3_vl_8b_qualification_v2.json`: 22/22 cases across two
repetitions. The earlier `qwen3_vl_8b_qualification.json` is retained as
evidence of benchmark defects that were corrected (a contradictory ladder
frame and an overly permissive vision scorer) and of the resulting deterministic
ready-landmark gate; it is not the final model score.

## Project server

Start:

```powershell
.\start_project_qwen3_vl_vulkan.ps1
```

Stop only the server recorded by this project:

```powershell
.\stop_project_qwen3_vl.ps1
```

The scripts do not change global Ollama, Vulkan, CUDA, or system settings. The
start script refuses to replace an already running `llama-server`; replacement
must be explicit.

## Promotion gate

1. Offline contract passes twice.
2. A low-action-limit Room-3 smoke test crosses the activated bridge and uses
   the west door without repeated tool use.
3. Secret Skills Cave is completed from the start twice.
4. Only then may testing expand to other dungeons or the overworld.
