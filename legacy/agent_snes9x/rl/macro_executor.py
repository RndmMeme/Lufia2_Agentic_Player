import time
import pydirectinput
from emulator.memory_reader import MemoryReader
from typing import Dict, Any

class MenuMacroExecutor:
    def __init__(self, key_map: Dict[int, str]):
        self.key_map = key_map
        self.menu_key = "s"  # Controller X in the current local mapping
        
    def _press(self, button_code: int, duration_sec: float =0.15, wait_after_sec: float =0.2):
        """Simulates a secure joypad button press for the emulator"""
        key = self.key_map.get(button_code)
        if not key:
            return
            
        pydirectinput.keyDown(key)
        time.sleep(duration_sec)
        pydirectinput.keyUp(key)
        time.sleep(wait_after_sec)

    def _press_named_key(self, key_name: str, duration_sec: float = 0.15, wait_after_sec: float = 0.2):
        if not key_name:
            return
        pydirectinput.keyDown(key_name)
        time.sleep(duration_sec)
        pydirectinput.keyUp(key_name)
        time.sleep(wait_after_sec)

    def use_item_on_character(self, item_name: str, target_character_index: int, game_state: Dict[str, Any]):
        """
        Executes the exact sequence to open the menu, navigate to an item, and use it.
        1. Open Menu (X)
        2. Select 'ITEM' (A)
        3. Navigate down to item_index
        4. Select Item (A)
        5. Navigate to character (Right x N) or (A if party char 1)
        6. Confirm (A)
        7. Exit Menu (B x 3)
        """
        inventory = game_state.get("inventory", [])
        
        # 1. Find the item in the live RAM list
        target_slot_index = -1
        for item in inventory:
            if item.get("item_name") == item_name:
                target_slot_index = item.get("slot_index")
                break
                
        if target_slot_index == -1:
            print(f"[MACRO] Failed. Item '{item_name}' not found in inventory.")
            return False
            
        print(f"[MACRO] Initiating sequence: Use {item_name} (Slot {target_slot_index}) on Char {target_character_index}")
        
        # 2. X -> Open Menu
        self._press_named_key(self.menu_key) # Controller X opens the menu
        time.sleep(0.5) # Wait for animation
        
        # 3. A -> Select 'ITEM' (Cursor defaults here)
        self._press(4) # 4 is A
        time.sleep(0.5) 
        
        # 4. Navigate down to the specific slot
        # The user confirmed the item list is a strict vertical column.
        # Pressing Down moves exactly 1 slot. Avoid L/R as they jump 10/20 items.
        for _ in range(target_slot_index):
            self._press(1) # 1 is Down
            
        # 5. Select the Item
        self._press(4) # A
        time.sleep(0.2)
        
        # 6. Apply to Character
        # Cursor jumps to Char 0.
        for _ in range(target_character_index):
            self._press(3) # 3 is Right
            
        # 7. Execute Application
        self._press(4) # A

        # 8. Escape Menu
        time.sleep(0.5)
        self._press(5) # B
        self._press(5) 
        self._press(5)
        self._press(5) # Press B multiple times to ensure we are back out
        
        return True
