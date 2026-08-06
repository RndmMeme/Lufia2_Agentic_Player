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

Every route and exploration direction is chosen by the model. The controller
may execute the selected direction as a short humanoid hold/batch, but map code
must not silently choose a corridor. Every tactical battle choice likewise
comes from the model: deterministic code exposes legal commands and advisory
facts, while non-tactical input execution and result-page advances remain
bounded machinery.

The local transport is provider-neutral: it probes Ollama, llama.cpp, then
KoboldCpp. The earlier Gemma E2B and other provider experiments remain
historical evidence, not the current default. The active design keeps one
multimodal model resident for planning and vision so LOOK does not trigger a
model swap. Cline is a development client, not a gameplay provider.

The current live baseline is `Qwen3-VL-4B-Spatial-Analysisv2.Q8_0.gguf` kept
resident on the RTX. The user-confirmed Run 29 latency and navigation result
belong to this CUDA/RTX path. The Intel Arc A770 Vulkan experiment took more
than 30 seconds per live decision and is not the active performance baseline.
Bridge transport and inference latency must be measured separately: the
persistent mailbox removes a repeated two-second Windows lock fallback, but it
does not explain or eliminate slow Vulkan image inference. A larger model is
not promoted until the 4B spatial model shows a repeatable capacity failure
with correct WRAM, map and visual context. Model calls remain serialized and
all GPU/backend choices are local to this project.

Dungeon tools and scenario keys have separate context policies. Every dungeon
decision sees all five tool states because tools solve puzzles and can stun
enemies. Scenario keys are consumed internally by access logic; the model sees
semantic reachable locations and a selected strategic goal, not raw flags or
missing-key lists.

Inventory visibility is also mode- and stage-specific. Exploration omits the
full inventory and rate-limits an explicit inventory retrieval to once per ten
minutes. At the battle action cross, the model receives curated subsets of
items actually owned (healing, MP recovery, revive, remedy, attack, control,
escape, defense and buff) so it can judge whether selecting Item is worthwhile.
Only after Item is selected does the legal-option payload contain every owned,
battle-usable item with quantity, effect and stable storage slot. Equipment and
other irrelevant inventory noise remain absent.

Planner, LOOK and tactical calls require schema-bound JSON immediately. The
current spatial baseline uses bounded output and no model swap between planning
and vision. Deliberate calls still receive a larger output budget and must
provide rationale, risk and contingency. The watchdog remains
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
