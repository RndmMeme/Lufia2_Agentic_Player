# Continual Harness

The continual harness lets the resident model propose bounded improvements from
real run evidence without granting it authority over Python, Mesen input,
curated facts, controller timing, safety gates, or dungeon reset rules.

## Modes

- Disabled (default): no refinement and no global harness state.
- Shadow: write run-local generations and collect globally reviewable
  candidates. Existing active canaries are deliberately invisible to the actor.
- Gated: do everything from Shadow, then activate only independently repeated
  candidates as measured canaries.

Start Shadow collection:

```powershell
python run_agent.py --execute --enable-llm --enable-harness-refiner
```

Start the complete gated lifecycle:

```powershell
python run_agent.py --execute --enable-llm --enable-harness-gated
```

Use an isolated state for a smoke test or A/B experiment:

```powershell
python run_agent.py --execute --enable-llm --enable-harness-gated `
  --harness-state-path data\runs\my_ab_test\global_harness.json
```

## Lifecycle

1. An event such as a verified loop, stall, room transition or milestone builds
   a bounded trajectory window from run artifacts.
2. The refiner returns schema-constrained proposals for `prompt_overlay`,
   `memory`, `skills`, or `subagents`. Every proposal cites real action indices.
3. The semantic validator rejects unsupported scopes, invented evidence,
   executable code, controller/reset expansion, safety-gate bypass language,
   invalid skill steps and unsafe subagent tools.
4. A proposal becomes eligible only after the same canonical proposal appears
   in at least two distinct runs by default.
5. In Gated mode an eligible `add` becomes an active canary. `update` and
   `retire` must name an active learned `target_id`; they cannot target curated
   or immutable state.
6. Active advice is included under `learned_harness`, explicitly below live
   WRAM, curated facts and safety rules. Skills are followed one normal intent
   at a time through the existing Thinking/Intent gates.
7. Each action exposed to a canary updates its reward metrics. A canary with at
   least four exposures, three consecutive non-positive outcomes and less than
   25 percent positive outcomes is automatically rolled back.

The shared state is `data/harness/continual_harness.json`. Run-local generation
evidence remains under `<run-dir>/harness_evolution/` and
`<run-dir>/harness_evolution.jsonl`.

## Runtime subagents

A subagent is a separate inference call to the same resident model, with its
own instructions, allowlist, turn limit and return condition. It is not a
second loaded model and never owns the controller. It may request only
allowlisted read-only `look`, `look_map`, or `retrieve` results and returns one
normalized advisory intent. The actor still decides, and the ordinary gates
still validate any action.

## Review and recovery

```powershell
python tools\harness_control.py status
python tools\harness_control.py promote <candidate-id> --reason "reviewed"
python tools\harness_control.py rollback <candidate-id> --reason "harmful"
```

`status` lists candidate state, scope, sightings, distinct runs and canary
metrics. Manual promotion is still bounded to learned candidates and cannot
modify the immutable runtime.
