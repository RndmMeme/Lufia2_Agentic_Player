# Granular Combat Decision Tree Implementation (Final)

Implement the exact combat decision tree and prompt structure provided by the user, including multi-stage branching, specific info requests, and character-level targeting.

## User Review Required

> [!IMPORTANT]
> This system replaces the current single-turn combat logic with a **recursive state machine** that allows the LLM to navigate menus, request info, and backtrack via `CANCEL`.

## Proposed Decision Tree & Prompts

### Phase 1: Pre-Battle Options
The system will present:
1. `[INFO]: PARTY` (Provide `party_status.md`)
2. `[INFO]: ENEMIES` (Provide `battle_briefing.md`)
3. `[BATTLE]: FIGHT`
4. `[BATTLE]: FLEE` (Omit if Boss Detected)
5. `[BATTLE]: SWAP`

**Branching Logic**:
- If **1 or 2**: Display requested file, then re-display remaining options.
- If **4**: Confirm and trigger `macro_executor.start_combat_round("flee")`.
- If **5**: Present **actual current party members**. Ask for `[TARGET]: [1st]` and `[TARGET]: [2nd]`. Execute swap macro, confirm, then return to Pre-Battle options.

---

### Phase 2: Fight (Character Turn)
For each character:
1. `[ATTACK]`: Attack normal.
2. `[SPELL]`: Cast Spell (Show list + costs. Omit if no MP/Spells).
3. `[IP]`: Use IP (Show list + costs. Omit if no IP/Items).
4. `[ITEM]`: Use item (Show inventory list).
5. `[DEFEND]`: Guard.
6. `[CANCEL]`: Backtrack logic (Previous char or Pre-Battle).

**Sub-Selection (Targeting)**:
- **Group**: Ask `[GROUP]: [ENEMY]` or `[GROUP]: [PARTY]`.
- **Target Type**: Ask `[TARGET]: [SINGLE]`, `[TARGET]: [MULTIPLE]`, or `[TARGET]: [ALL]`.
- **Cancel**: Always provide `[CANCEL]` to change target or abort action.
- **Verification**: Check if character is afflicted (Dead, Paralyzed, Sleep, Silence) to determine action eligibility.

---

### Phase 3: Macro Execution
- **Reuse existing macros** in [battle_macro.py](file:///d:/Projects/AI_Emu_Player/agent/rl/battle_macro.py) (e.g., [select_attack](file:///d:/Projects/AI_Emu_Player/agent/rl/battle_macro.py#91-99), [select_spell](file:///d:/Projects/AI_Emu_Player/agent/rl/battle_macro.py#144-166)).
- **Targeting**: Press A -> Direction (Target-1) -> Press A.
- **Flee**: Hold Down + A.
- **Swap**: Hold Up + A (Target 1) -> Down -> A (Target 2).

---

### Phase 4: Boss Detection
1. Scan `emulator/sprites/bosses` for active boss sprites.
2. If unknown but `No_Escape.png` appears during a flee attempt, mark as Boss and disable FLEE in future rounds.

## Implementation Steps

1. **Refactor `CombatStateManager`**: Support recursive states, dynamic party info, and backtracking.
2. **Update `IntelSynthesizer`**: Generate the exact prompt text and handle dynamic lists (Spells/IP/Items).
3. **Update Orchestrator**: Implement the "Wait for decision" loop in `main.py`.
