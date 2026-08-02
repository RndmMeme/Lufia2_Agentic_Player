# Mesen-only target architecture

## Control loop

1. Mesen Lua supplies coherent WRAM snapshots, screenshots, and frame-bounded
   controller input.
2. A deterministic decoder turns WRAM into a compact game-state model.
3. Reflex gates handle invariants: battle detection, menus, blocked movement,
   action/time limits, stale observations, and map-boundary checks.
4. Navigation and battle planners propose bounded actions from verified state.
5. The LLM is called for tactical battle choices and for goals, ambiguity,
   puzzles, recovery, and strategy.
6. `LOOK` supplies an event-driven frame plus WRAM/map semantics when visual
   classification is necessary.
7. Every action is verified against the following WRAM observation and written
   to a resumable journal.

Controller taps use the shared humanoid profile: held for 2 emulated frames
(about 33 ms), followed by an explicit neutral release and at least 320 ms for
animation and observation. The cursorless battle action cross is the confirmed
exception: hold the direction for 2 lead frames, add A for 2 frames, then release
both. Lists and target selectors use simple taps; R is tapped once for all targets.
Exploration uses a short continuous direction hold (12 frames by default) before
the next WRAM observation. Battle results hold A continuously and release only
when `7E:09AA` reports that battle mode ended, with a 3600-frame safety ceiling.

## Authority order

1. Successful or failed WRAM-observed transition
2. Curated map/object annotation
3. ROM tables and confirmed WRAM base of truth
4. VLM classification with confidence
5. Walkthrough/RAG guidance
6. LLM hypothesis

Visual appearance never overrides a contradictory movement observation. A
failed directed movement is `blocked_now`, not automatically a permanent wall.

Room reset is a gated recovery macro: one humanoid `Select` tap, one `Up` tap to
select the hourglass, then one `A` tap. The runtime re-reads map and position
afterward and expires only momentary collisions from the current curated room.
The confirmed mode sequence is tool/reset menu `04` or `05`, hourglass
confirmation `00`, then exploration `01`. A reset may change the reported
position and respawn actors, so the post-reset observation is authoritative.

## LLM harness

The model must return one schema-validated intent. The harness converts that
intent into a small, reversible action batch. Invalid, stale, overlong, or
out-of-state intents are rejected. The model cannot send arbitrary key streams,
filesystem operations, shell commands, or unbounded loops.

Normal corridors should not require model calls. Every tactical battle choice
does: deterministic code exposes legal commands and advisory facts, while the
model selects the move. Non-tactical execution waits and result-page advances
remain deterministic.

The local transport is provider-neutral: it probes Ollama, llama.cpp, then
KoboldCpp. Planning and vision may use different models, but the current
default deliberately uses the same Gemma 4 E2B IT Q4 for both roles. Ollama
reports tools, completion, vision and audio capabilities, 4.65B total
parameters and Q4_K_M quantization. A live contract benchmark showed reliable
exploration intents and schema-valid visual output; Gemma 3 4B failed every
planner case. E2B avoids a model swap before LOOK, while larger Gemma and Qwen
models remain fallback candidates. Cline is a development client, not a
gameplay provider.

Ollama targets the Intel Arc A770 eGPU with 16 GB VRAM through Vulkan. The
internal RTX 5070 Laptop GPU and Radeon 880M are not the intended inference
path. Capacity is treated as headroom, not a target: Ollama uses a strict
single-resident policy and the shared Gemma model avoids the roughly 13.5 GB
base-weight footprint of keeping Gemma and Qwen resident together. Planner
requests use a 3072-token context, LOOK uses 4096 tokens, and the shared Gemma
instance may stay resident for two minutes. Model calls are serialized. If
benchmarks show memory pressure, context size is reduced before model size is
increased.

Planner, LOOK and tactical calls require schema-bound JSON immediately. The
current Gemma-4-E2B Ollama build explicitly rejects the `think` API flag, so
model-internal thinking is disabled for it. Deliberate calls still receive the
larger 4096-token/480-output budget and must provide rationale, risk and
contingency. The 30-second watchdog and 120-second stale-decision ceiling remain
active; a future model may enable internal thinking only if its API advertises
and passes that contract.

## Battle safety gate

The old repeated-A battle routine is retained only as a low-level input smoke
helper and is never called by the autonomous orchestrator. Battles fail closed
until a legal-action planner has decoded the active actor, command/menu phase,
targets, HP/MP/IP, statuses, usable spells, items and enemy damage semantics.
The menu decoder generates a bounded legal action set. Survival/resource code
adds advisory facts but does not choose or rank the final move in production.
The LLM must select one offered `option_id`, explain its risk and provide a
contingency; the gate rejects invented commands, targets, costs and raw button
sequences. This deliberately leaves tactics and RNG-aware judgment to the LLM:
healing timing, a low-HP finisher when recovery is exhausted, learned physical
ineffectiveness, elemental magic, items/IP, defend/flee and non-casters.
