# Task: Implement Granular Combat Decision Tree (Literal)

- [ ] Refactor [CombatStateManager](file:///d:/Projects/AI_Emu_Player/main.py#117-148) (Recursive State Machine) [/]
    - [ ] Add `PRE_BATTLE`, `SHOWING_INFO`, `PICKING_SWAP`, `GATHERING_ACTIONS`, `TARGETING` modes
    - [ ] Implement `CANCEL` backtracking logic (revoking previous char actions)
- [ ] Update [IntelSynthesizer](file:///d:/Projects/AI_Emu_Player/agent/intel_synthesizer.py#4-322) (Literal Prompting) [ ]
    - [ ] Implement `Phase 1: Pre-Battle` exact options (1-5)
    - [ ] Implement `Phase 2: Fight` exact options (1-6)
    - [ ] Implement `Sub-Selection: Targeting` (Group/Target/Type)
    - [ ] Show costs/amounts/eligible targets per character
- [ ] Enhance Orchestrator Loop [main.py](file:///d:/Projects/AI_Emu_Player/main.py) [ ]
    - [ ] Handle immediate info-re-prompting
    - [ ] Implement `[SWAP]` interaction flow
    - [ ] Integrate granular targeting macros
- [ ] Implement Boss Detection [ ]
    - [ ] Sprite scan `emulator/sprites/bosses`
    - [ ] `No_Escape.png` fallback
- [ ] Final verification and walkthrough [ ]
