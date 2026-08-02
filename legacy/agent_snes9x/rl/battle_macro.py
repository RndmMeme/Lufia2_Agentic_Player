import time
import pydirectinput
import logging
import pygetwindow as gw
from typing import Dict, Any, List, Optional
from agent.runtime_config import get_emulator_window_title

# Constant for SNES "Hold Direction + Button" duration to ensure emulator registers it.
BATTLE_HOLD_DURATION = 0.55

class BattleMacroExecutor:
    """
    Executes precise combat sequences in Lufia 2 based on the AI's high-level intent.
    Assumes the emulator is focused and the Battle Menu is actively waiting for input on "Fight".
    """
    def __init__(self, key_map: Dict[int, str]):
        # action_map in environments typically maps integer IDs to keyboard strokes.
        # e.g., 0: 'up', 1: 'down', 2: 'left', 3: 'right', 4: 'x' (A in SNES), 5: 'z' (B), 8: 'd' (R)
        self.key_map = key_map
        self.window_title = get_emulator_window_title()

    def _ensure_emulator_focus(self):
        windows = gw.getWindowsWithTitle(self.window_title)
        if not windows:
            logging.warning("MOVE INPUT: emulator window with title containing '%s' was not found.", self.window_title)
            return False

        window = windows[0]
        try:
            if not window.isActive:
                window.activate()
                time.sleep(0.15)
        except Exception as exc:
            logging.warning("MOVE INPUT: failed to activate emulator window: %s", exc)

        active_title = None
        try:
            active_title = gw.getActiveWindowTitle()
        except Exception:
            active_title = None

        is_active = bool(window.isActive)
        logging.info("MOVE INPUT: target_window='%s' active=%s active_title='%s'", window.title, is_active, active_title)
        return is_active
        
    def _press(self, button_code: int, duration_sec: float = 0.15, wait_after_sec: float = 0.25):
        """Simulates a secure joypad button press for the emulator"""
        key = self.key_map.get(button_code)
        if not key:
            print(f"[MACRO ERROR] Unknown button code: {button_code}")
            return
            
        pydirectinput.keyDown(key)
        time.sleep(duration_sec)
        pydirectinput.keyUp(key)
        time.sleep(wait_after_sec)

    def _press_named_key(self, key_name: str, duration_sec: float = 0.18, wait_after_sec: float = 0.12):
        """Press a key by its string name (e.g. 'up', 'left', 'x'). Used for exploration movement."""
        if not key_name:
            return
        if not self._ensure_emulator_focus():
            logging.warning("MOVE INPUT: skipping key '%s' because emulator is not focused.", key_name)
            return
        logging.info("MOVE INPUT: pressing key '%s' for %.2fs", key_name, duration_sec)
        pydirectinput.keyDown(key_name)
        time.sleep(duration_sec)
        pydirectinput.keyUp(key_name)
        time.sleep(wait_after_sec)

    def _hold_and_press(self, hold_button_code: int, press_button_code: int, duration_sec: float = BATTLE_HOLD_DURATION):
        """Holds a direction while pressing another button (required for Lufia 2 cross menu)."""
        hold_key = self.key_map.get(hold_button_code)
        press_key = self.key_map.get(press_button_code)
        if not hold_key or not press_key:
            return
            
        pydirectinput.keyDown(hold_key)
        time.sleep(0.1)
        pydirectinput.keyDown(press_key)
        time.sleep(0.12) # Brief tap for the command button
        pydirectinput.keyUp(press_key)
        
        # Continue holding the direction for the remaining duration (to ensure emulator registers fleeing)
        remaining_hold = max(0, duration_sec - 0.18)
        if remaining_hold > 0:
            time.sleep(remaining_hold)
            
        pydirectinput.keyUp(hold_key)
        time.sleep(0.25)

    def start_combat_round(self, action: str = "fight", swap_idx_1: int = 0, swap_idx_2: int = 1):
        """
        Handles the initial Pre-Battle Menu (Top/Center/Bottom) at the start of every combat turn.
        Actions: "fight" (Center), "flee" (Bottom), "change_position" (Top)
        """
        print(f"[BATTLE MACRO] Starting Combat Round: {action.upper()}")
        
        if action == "fight":
             # Fight is the default center option. Just press A.
             self._press(4)
             time.sleep(0.4)
        elif action == "flee":
             # Hold Down + A to Flee
             self._hold_and_press(1, 4)
             time.sleep(0.4)
        elif action == "change_position":
             # Hold Up + A to enter Swap Mode
             self._hold_and_press(0, 4)
             time.sleep(0.4)
             # Select first character (defaults to top left)
             for _ in range(swap_idx_1):
                  self._press(3) # Right
             self._press(4) # Confirm Char 1
             time.sleep(0.2)
             # Select second character
             for _ in range(swap_idx_2):
                  self._press(3) # Right
             self._press(4) # Confirm Char 2
             time.sleep(0.4)

    def open_swap_menu(self):
        """Open the pre-battle change-position screen without selecting anyone yet."""
        print("[BATTLE MACRO] Opening Swap Menu")
        self._hold_and_press(0, 4)
        time.sleep(0.4)

    def _move_swap_cursor(self, start_slot: int, target_slot: int):
        """Move across the 2x2 party layout: 1 2 / 3 4."""
        start_slot = max(1, min(4, int(start_slot)))
        target_slot = max(1, min(4, int(target_slot)))

        start_row = (start_slot - 1) // 2
        start_col = (start_slot - 1) % 2
        target_row = (target_slot - 1) // 2
        target_col = (target_slot - 1) % 2

        while start_row < target_row:
            self._press(1)
            start_row += 1
        while start_row > target_row:
            self._press(0)
            start_row -= 1
        while start_col < target_col:
            self._press(3)
            start_col += 1
        while start_col > target_col:
            self._press(2)
            start_col -= 1

    def swap_positions(self, first_slot: int, second_slot: int):
        """Execute a party swap in the 2x2 formation grid."""
        print(f"[BATTLE MACRO] Swapping positions {first_slot} and {second_slot}")
        self._move_swap_cursor(1, first_slot)
        self._press(4)
        time.sleep(0.2)
        self._move_swap_cursor(first_slot, second_slot)
        self._press(4)
        time.sleep(0.4)

    def cancel_action(self, num_times: int = 1):
        """
        Presses B to cancel the current character's action, or back out to the pre-battle menu.
        Warning: Backing out to the pre-battle menu cancels ALL previously made character decisions for this round.
        """
        print(f"[BATTLE MACRO] Canceling Action ({num_times} times)")
        for _ in range(num_times):
            self._press(5) # B - Cancel
            time.sleep(0.3)

    def select_attack(self, target_enemy_idx: int = 0):
        """Center menu option: Standard physical attack."""
        print(f"[BATTLE MACRO] Executing Attack on enemy {target_enemy_idx}")
        self._press(4) # A - Select Attack
        time.sleep(0.3)
        for _ in range(target_enemy_idx):
             self._press(3) # Right - navigate enemy targets
        self._press(4) # A - Confirm target

    def select_defend(self):
        """Right menu option: Defend."""
        print("[BATTLE MACRO] Executing Defend")
        self._hold_and_press(3, 4) # Hold Right + Press A - Confirm Defend

    def select_ip_attack(self, slot_idx: int = 1, target_enemy_idx: int = 0, target_all: bool = False):
        """
        Down menu option: IP Attack.
        slot_idx: 1-6 corresponding to the equipment slot.
        """
        print(f"[BATTLE MACRO] Executing IP Attack (Slot: {slot_idx}, Target All: {target_all})")
        self._hold_and_press(1, 4) # Hold Down + Press A - Open IP list
        time.sleep(0.5)
        
        # IP skills list ALWAYS starts at the top when opening.
        # So the target IP Macro is (target - 1) presses down.
        for _ in range(slot_idx - 1):
            self._press(1) # Down
            time.sleep(0.2)
            
        self._press(4) # A - Select highlighted IP move
        time.sleep(0.5)
        
        if target_all:
             self._press(8) # R - Toggle All
             self._press(4) # A - Confirm Target
             return

        for _ in range(target_enemy_idx):
             self._press(3) # Right - Navigate targets
        self._press(4) # A - Lock target
        time.sleep(0.18)
        self._press(4) # A - Final confirm and advance

    def open_ip_menu(self):
        """Open the battle IP menu without selecting an action yet."""
        print("[BATTLE MACRO] Opening IP Menu")
        self._hold_and_press(1, 4) # Hold Down + Press A
        time.sleep(0.5)

    def scroll_ip_menu_for_scan(self, downs: int):
        """Move down through the IP list for scan purposes."""
        for _ in range(max(0, int(downs))):
            self._press(1, duration_sec=0.08, wait_after_sec=0.15)

    def close_menu_level(self):
        """Close the currently open submenu with a single B press."""
        self._press(5, duration_sec=0.10, wait_after_sec=0.20)

    def select_item(self, downs_to_item: int, target_idx: int = 0, target_all: bool = False, target_is_enemy: bool = False):
        """Left menu option: Item."""
        print(f"[BATTLE MACRO] Executing Item (Downs: {downs_to_item}, Target All: {target_all})")
        self._hold_and_press(2, 4) # Hold Left + Press A - Open Item list
        time.sleep(0.4)

        # Do not trust the remembered item cursor position; normalize first.
        self._normalize_vertical_menu_top()

        for _ in range(downs_to_item):
             self._press(1) # Down
             
        self._press(4) # A - Confirm Item
        time.sleep(0.4)
        
        if target_all:
             self._press(8) # R - Toggle All
        else:
             # Navigating to characters vs enemies depends on the item type's default focus.
             # Typically heals default to Party 1, damage items default to Enemy 1.
             # Toggling faction might require pressing Down/Up? (Assuming simple horizontal navigation for now)
             for _ in range(target_idx):
                  self._press(3) # Right
                  
        self._press(4) # A - Confirm Target

    def _normalize_spell_cursor_top_left(self, max_rows: int = 20):
        """
        Force the spell menu cursor to the top-left entry.
        The game may reopen the spell list on the last-used spell, so we first
        walk to the top of the current column and then push left into column 1.
        """
        for _ in range(max_rows):
            self._press(0, duration_sec=0.08, wait_after_sec=0.08) # Up
        self._press(2, duration_sec=0.08, wait_after_sec=0.08) # Left
        self._press(2, duration_sec=0.08, wait_after_sec=0.08) # Left again just in case

    def _normalize_vertical_menu_top(self, max_rows: int = 40):
        """Force a single-column cursor to the top entry."""
        for _ in range(max_rows):
            self._press(0, duration_sec=0.08, wait_after_sec=0.08) # Up

    def select_spell(
        self,
        downs_to_spell: int,
        is_right_column: bool = False,
        target_idx: int = 0,
        target_all: bool = False,
        target_indices: Optional[List[int]] = None,
    ):
        """Up menu option: Spell."""
        print(f"[BATTLE MACRO] Executing Spell (Downs: {downs_to_spell}, Right Col: {is_right_column})")
        self._hold_and_press(0, 4) # Hold Up + Press A - Open Spell list
        time.sleep(0.4)

        # Do not trust the remembered cursor position; normalize first.
        self._normalize_spell_cursor_top_left()
        
        if is_right_column:
             self._press(3) # Right to switch to second column
             
        for _ in range(downs_to_spell):
             self._press(1) # Down
             
        self._press(4) # A - Confirm Spell
        time.sleep(0.4)
        
        if target_all:
             self._press(8) # R - Toggle All
             self._press(4) # A - Confirm Target
             return

        chosen_targets = target_indices[:] if target_indices else [target_idx]
        if not chosen_targets:
            chosen_targets = [0]

        current_target_idx = 0
        for idx, desired_target_idx in enumerate(chosen_targets):
            desired_target_idx = max(0, int(desired_target_idx))
            while current_target_idx < desired_target_idx:
                self._press(3) # Right
                current_target_idx += 1
            while current_target_idx > desired_target_idx:
                self._press(2) # Left
                current_target_idx -= 1
            self._press(4) # A - Lock in current target
            time.sleep(0.18)
            if idx == len(chosen_targets) - 1:
                self._press(4) # A - Final confirm and advance to next character

    def skip_results(self, max_duration_sec: float = 4.5, press_interval_sec: float = 0.22):
        """Mash A through the battle result window until the map is ready again."""
        print("[BATTLE MACRO] Skipping Battle Results")
        if not self._ensure_emulator_focus():
            logging.warning("RESULT INPUT: emulator not focused, cannot skip results.")
            return

        deadline = time.time() + max_duration_sec
        while time.time() < deadline:
            self._press(4, duration_sec=0.08, wait_after_sec=press_interval_sec)
