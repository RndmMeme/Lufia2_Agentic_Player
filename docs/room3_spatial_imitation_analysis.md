# Room 3: Codex reference run and spatial imitation structure

This document reconstructs how the completed Codex-guided reference run passed
Room 3 of the Secret Skills Cave. It deliberately separates observed evidence,
later-confirmed coordinates, reconstruction and transferable policy.

## Evidence boundary

The reference run under `data/runs/codex_reference_cave/` contains timestamped
screenshots but no action journal or preserved private chain of thought. Exact
button counts between every screenshot therefore cannot be recovered. The
sequence below combines:

- timestamped reference screenshots;
- corrections supplied by the user during the live run;
- confirmed WRAM landmarks in
  `data/navigation_objectives/secret_skills_cave_room_sweep.json`;
- the confirmed bridge tile-buffer states;
- Run 29's journal, which exposes the smaller model's contrasting failure mode.

The landmark coordinates are ground truth established after the reference run.
Any statement about Codex's unlogged internal thought is explicitly marked as a
reconstruction rather than a verbatim reasoning trace.

## Distilled successful route

Room 3 is one stateful spatial task with three successive subgoals. Map ID `5`
does not change between the cave's internal rooms.

### Phase A: activate the bridge

Start condition:

- entering from the south/Room 2;
- bridge tiles are inactive: `[02, 22, 20]`;
- Arrow is owned and selected.

Spatial target:

- firing position: live feet `(28,24)`;
- required facing: west.

Policy demonstrated by the successful run:

1. Move north along the open central approach until the feet reach `(28,24)`.
2. Turn west without moving.
3. Use Arrow exactly once.
4. Do not infer success merely from the animation. Verify the semantic
   map-buffer transition to active `[00, 02, 00]` and/or the newly completed
   plank bridge.

Reference images:

- `room3_entry_settled.png`
- `room3_before_arrow.png`
- `room3_after_arrow.png`

### Phase B: align with and cross the bridge

Start condition:

- bridge is confirmed active;
- actor is still near `(28,24)`.

Spatial target:

- left side of the bridge: live feet `(21,26)`.

Policy demonstrated by the successful run:

1. Move south to the bridge row at `y=26`; west from the firing row is blocked
   by terrain and is not the bridge crossing.
2. Move west across the visible completed planks.
3. Confirm success by WRAM position reaching the left bank, not by assuming a
   long west input completed in full.

Reference images:

- `room3_south_to_bridge.png`
- `room3_bridge_try.png`
- `room3_across_bridge.png`

### Phase C: reach and traverse the west door

Start condition:

- actor is on the left bank near `(21,26)`.

Spatial target:

- west-door approach: live feet `(17,23)`;
- required traversal direction: north.

Policy demonstrated by the successful run:

1. A direct west move from `(21,26)` is blocked. Move north along the bank to
   the corridor row `y=23`.
2. Move west along that row until the feet reach the door approach `(17,23)`.
3. Move north through the door. Do not press `A` and do not use a tool: normal
   cave doors are crossed by movement through their north-south threshold.
4. Confirm the transition from coordinate discontinuity/new room layout. Do
   not use unchanged `map_id=5` as room evidence.

Reference images:

- `room3_across_bridge.png`
- `room3_crosspass_y23.png`
- `room3_leftdoor_below.png`
- `room4_actual_entry.png`

## What Codex did well

- It decomposed the puzzle into an interaction, a state verification and
  navigation after the world changed.
- It used feet position as the collision/alignment anchor.
- It eventually treated the completed bridge as a new traversable route rather
  than repeatedly firing Arrow.
- Once the hidden west corridor was correctly identified, it aligned beneath
  the door and traversed it with movement.
- It accepted feedback after failed movement and changed the local hypothesis.

## What Codex did poorly

The screenshot timestamps show that activating and crossing the bridge took
about three minutes, while finding the correct west door took roughly eight
additional minutes. The latter was not efficient autonomous reasoning; it was
successful human-guided recovery.

- Codex treated the current viewport as if it contained the whole relevant
  room. The west transit corridor is not visible until approached/entered.
- It called the red wall sprite at the north end an exit. The user corrected it
  to a torch. A red wall object is not a door merely because it is salient.
- It tried the visible northern area and backtracked repeatedly instead of
  preserving the room-level west-door target.
- It did not initially distinguish the bridge row from the firing row.
- It struggled to align screenshot-map positions with WRAM coordinates and
  needed the user to provide depth/anchor corrections.

These errors must not be copied into an imitation trace. They should become
short negative examples and guardrails.

## What Run 29 received and why it failed late

Run 29 proved the 4B spatial model can perform most individual substeps. It
reached live `(19,23)`, two tiles before the real west-door approach.

Its useful behavior included:

- approaching the firing landmark;
- eventually using Arrow at the correct position;
- finding the bridge row and reaching `(21,26)`;
- moving north and then west toward the actual door row.

Its context failures were more important than its model size:

- ordinary intent calls were logged as `structured_state_only`; screenshots
  were requested reactively after stalls;
- `navigation_map.ascii_crop` was actually `null` because the cave navigation
  map uses `runtime_alignment=room_landmarks`;
- visual LOOK results repeatedly contradicted the already-confirmed bridge
  state and encouraged more Arrow shots;
- the old room bounds falsely labeled `(20,25)` as Room 4, injecting the Room 4
  pillar objective while the actor was still in Room 3;
- this false room transition was rewarded, reinforcing hallucinated progress.

The room-boundary bug is now covered by a regression test, but the missing
live-aligned local map remains an open transfer problem.

## Compact target structure for the spatial model

Run 30 showed that the smaller model does not need a prescribed route. Given a
loose room goal, it independently reached the firing point, faced correctly,
used Arrow, reacted to a blocked direct west move and found the southern bridge
row. The default prompt should therefore expose the next observable target and
let the model choose the route.

The normal target card should remain well below 300 tokens:

```json
{
  "room": "secret_skills_cave.room_3",
  "goal": "reach the next room through the west door via (17,23)",
  "current": {
    "feet": [28, 24],
    "facing": "west",
    "blocked_direction": null,
    "bridge": "inactive | active"
  },
  "target": {
    "feet": [28, 24],
    "facing": "west",
    "success_signal": "map-buffer state or confirmed transit"
  },
  "actor_local_sensor": "ACTOR_LOCAL_3X3",
  "confirmed_world_changes": "action-linked POST_ACTION_EFFECT_REGION when present",
  "last_outcome": "open | blocked_now | semantic_change",
  "success_signal": "confirmed transit, not unchanged map_id"
}
```

Specific route facts, negative examples and reference poses are escalation
material, not default instructions. Add one only after repeated failure at the
same observable subgoal.

## Transfer with existing project components

### 1. Phase-select one reference pose

Reuse the existing reference screenshots, but send only the one relevant to the
current phase:

- inactive bridge -> `room3_before_arrow.png`;
- active bridge/right bank -> `room3_south_to_bridge.png`;
- active bridge/left bank -> `room3_crosspass_y23.png`;
- near west door -> `room3_leftdoor_below.png`.

The current multi-frame client must distinguish roles explicitly:

- `PREVIOUS_LIVE`
- `CURRENT_LIVE`
- `REFERENCE_TARGET`

A reference image must never be labeled as a newer live frame.

### 2. Replace the absent ASCII crop with a live-coordinate micro-map

The stitched map cannot currently be indexed directly by WRAM coordinates.
Until a full transform is proven, build a Room-3 micro-map from confirmed live
landmarks and confirmed/discovered edges. It needs only:

- player feet `@`;
- firing point `F`;
- active/inactive bridge row `=` or gap;
- left-bank waypoint `L`;
- west-door approach `D`;
- blocked edges already observed.

This is smaller and more truthful than pretending the stitched 16x16 grid is
live-aligned. The existing `OnlineNavigationMapper` already records open and
blocked directed edges; the room objective supplies `F`, `L` and `D`.

### 3. Give state changes priority over fresh visual guesses

Use the existing confirmed bridge decoder as authoritative. Once the bridge
state is active, remove `use_tool` as a valid Room-3 puzzle action and label the
Arrow landmark complete. Vision may describe the scene, but it cannot revert a
confirmed semantic state without a later contradictory map-buffer change.

### 4. Use two positive and three negative demonstrations

Positive examples:

- at `(28,24)`, west-facing, inactive -> `use_tool` once;
- at `(21,26)`, active, west blocked -> move north toward `y=23`.

Negative examples:

- active bridge -> another Arrow shot is wrong;
- red northern wall sprite -> not a door;
- one-tile move with unchanged map ID -> not proof of a room transition.

These examples can extend `data/benchmarks/lufia_agent_contract_v1.json` before
they are promoted into the live prompt.

### 5. Reward only observable subgoal completion

Use the existing feedback ledger, but reward only:

- reaching the firing pose;
- confirmed inactive-to-active bridge transition;
- reaching the left bank;
- reaching `(17,23)`;
- confirmed door transit.

Penalize repeated completed actions, unchanged-position movement, and claims of
a room transition without transit evidence. Do not reward merely entering a
different overlapping room bound.

## Recommended implementation order

1. Keep room goals minimal: target coordinate or next-room transit coordinate.
2. Send the actor-centered `ACTOR_LOCAL_3X3` on every exploration decision.
3. After a world-changing action, send explicit PREVIOUS/CURRENT frames plus a
   persisted `POST_ACTION_EFFECT_REGION` around the changed remote tiles.
4. Add a live-coordinate micro-map or reference pose only as stall escalation.
5. Extend the offline contract with bridge-row, left-bank, torch and true-door
   cases.
6. Run a no-input qualification against the current 4B Spatial Q8.
7. Only after it passes, repeat Room 3 live twice from the same initial state.

No larger model is justified until this compact imitation context has been
tested.

## Live stall found while validating this analysis

Run 30 did not move at all: it repeatedly requested `look` until the reasoning
step limit. This was a context bug, not an emulator, Lua-bridge or model-server
failure.

- WRAM byte `$1272` retains the direction of the last collision. At the next
  runner start it still said `north`, although north from `(28,30)` was open.
- The harness exposed that stale value as a current obstacle, so the direct
  route to `(28,24)` appeared illegal.
- `look` remained available after an unchanged observation, allowing the model
  to keep asking for more images without gaining information.

The model-facing blocked direction is now emitted only when the immediately
preceding move requested that direction and produced no position change.
`look` and `look_map` are each offered only once per unchanged emulator state;
movement or another state-changing action makes perception available again.

Run 31 verified the correction live with the current Qwen Spatial Q8 model. In
two decisions it chose north twice and moved `(28,30) -> (28,29) -> (28,28)` in
6.391 seconds. This also establishes an important global lesson: retained WRAM
event bytes need causal validation against the action journal before they are
presented as current world state.
