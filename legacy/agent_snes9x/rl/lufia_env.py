import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pydirectinput
import time
import logging
from emulator.memory_reader import MemoryReader
from typing import Optional
import pygetwindow as gw
from agent.rl.exploration_manager import ExplorationManager
from agent.runtime_config import get_emulator_window_title

class Lufia2Env(gym.Env):
    """Custom Environment that follows gym interface"""
    metadata = {'render.modes': ['human']}

    def __init__(self, render_mode: Optional[str] = None):
        super(Lufia2Env, self).__init__()
        self.render_mode = render_mode
        self.reader = MemoryReader()
        self.window_title = get_emulator_window_title()
        
        # Discrete actions: Up, Down, Left, Right, A, B, Y, L, R
        # Removed X (Menu), Start, Select from RL agent to prevent getting stuck in menus.
        # Menus will be handled exclusively by the LLM Macro Engine!
        self.action_space = spaces.Discrete(9)
        
        # Observation Space: X, Y, DungeonX, DungeonY, DungeonBlocking, MapID, AvgHP, AvgMP, InBattleFlags, AvgMaxHP, TargetDX, TargetDY
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]), 
            high=np.array([255, 255, 65535, 65535, 255, 9999, 9999, 999, 1, 9999, 65535, 65535]), 
            dtype=np.float32
        )
        
        self.target_dx = 0.0
        self.target_dy = 0.0
        self.state = None
        self.last_target_dist = 99999.0
        self.explorer = ExplorationManager() # Optional persistent explorer

    def _state_to_obs(self, raw_state):
        self.raw_state = raw_state

        # Mapping from JSON
        x = float(raw_state.get("x", 0))
        y = float(raw_state.get("y", 0))
        d_x = float(raw_state.get("dungeon_x", 0))
        d_y = float(raw_state.get("dungeon_y", 0))
        d_block = float(raw_state.get("dungeon_blocking", 255))
        map_id = float(raw_state.get("map_id", 0))
        
        # Dynamic HP / MP
        party_hp = raw_state.get("hp", [0])
        party_mp = raw_state.get("mp", [0])
        
        # We need Max HP to calculate percentages
        party_max_hp = raw_state.get("max_hp", [100])
        avg_max_hp = float(sum(party_max_hp) / len(party_max_hp)) if party_max_hp else 100.0
        
        avg_hp = float(sum(party_hp) / len(party_hp)) if party_hp else 0.0
        avg_mp = float(sum(party_mp) / len(party_mp)) if party_mp else 0.0
        
        # Extract battle state from dedicated flag
        in_battle = 1.0 if raw_state.get("in_battle", False) else 0.0
        
        return np.array([x, y, d_x, d_y, d_block, map_id, avg_hp, avg_mp, in_battle, avg_max_hp, self.target_dx, self.target_dy], dtype=np.float32)

    def _state_has_live_exploration_data(self, raw_state):
        if not isinstance(raw_state, dict):
            return False
        if raw_state.get("map_id", 0):
            return True
        if raw_state.get("map_name") not in (None, "", "Unknown", "Unknown Map (00)"):
            return True
        if raw_state.get("dungeon_x", 0) or raw_state.get("dungeon_y", 0):
            return True
        if raw_state.get("x", 0) or raw_state.get("y", 0):
            return True
        return False

    def set_target(self, dx, dy):
        """Allows the Orchestrator to define the agent's spatial goal."""
        self.target_dx = float(dx)
        self.target_dy = float(dy)
        # Recalculate base distance so we don't accidentally penalize the first step
        if self.state is not None:
            self.last_target_dist = abs(self.state[2] - self.target_dx) + abs(self.state[3] - self.target_dy)

    def _get_obs(self):
        """Fetches memory from the emulator and frames it for the PyTorch model."""
        raw_state = self.reader.get_game_state()
        return self._state_to_obs(raw_state)

    def refresh_state(self, wait_for_live=False, timeout_sec=1.0, poll_interval=0.05):
        deadline = time.time() + max(0.0, timeout_sec)
        latest_raw_state = None

        while True:
            latest_raw_state = self.reader.get_game_state()
            self.state = self._state_to_obs(latest_raw_state)

            if not wait_for_live or self._state_has_live_exploration_data(latest_raw_state):
                return latest_raw_state

            if time.time() >= deadline:
                return latest_raw_state

            time.sleep(poll_interval)

    def _get_info(self, refresh=False, wait_for_live=False, timeout_sec=1.0, poll_interval=0.05):
        if refresh:
            return self.refresh_state(
                wait_for_live=wait_for_live,
                timeout_sec=timeout_sec,
                poll_interval=poll_interval
            )
        if hasattr(self, 'raw_state'):
            return self.raw_state
        return {"gold": 0}

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # We don't strictly 'reset' the emulator here usually. Instead, we can let it play on,
        # or we might need an input command to load a save state for strict episodic learning.
        # For agentic play, it's continuous.
        
        info = self.refresh_state(wait_for_live=False)
        return self.state, info

    def step(self, action):
        """Applies action to the emulator, advances a frame, reads new state."""
        # Action Map (A=x, B=z, Y=a, L=q, R=w)
        action_map = {
            0: 'up',
            1: 'down',
            2: 'left',
            3: 'right',
            4: 'x', # User mapped to 'x' for A
            5: 'z', # User mapped to 'z' for B
            6: 'a', # User mapped to 'a' for Y
            7: 'q', # User mapped to 'q' for L
            8: 'w'  # User mapped to 'w' for R
        }
        
        key = action_map.get(action)
        
        # ONLY send inputs if Snes9x is the active window to prevent OS-wide typing!
        snes_windows = gw.getWindowsWithTitle(self.window_title)
        is_focused = snes_windows and snes_windows[0].isActive
        
        if key and is_focused:
            print(f"[RL_ENV] Pressing key: {key}") # Debug print to see what agent is doing
            pydirectinput.keyDown(key)
            time.sleep(0.15) # Increased duration to ensure emulator registers it
            pydirectinput.keyUp(key)
            
        # Give emulator time to process the frame
        time.sleep(0.1) 
        
        # Read new state
        self.state = self._get_obs()
        
        # 4. Calculate reward (Reward shaped by LLM Goal!)
        reward = 0.0 
        
        # Evaluate Context Needs for Menu (HP, Status Ailments, New Equipment, Capsule Monsters)
        avg_hp = self.state[6]
        avg_max_hp = self.state[9]
        
        needs_healing = (avg_hp <= (0.5 * avg_max_hp)) and (avg_max_hp > 0)
        
        # TODO: Extract these from GameState / WRAM later
        needs_status_cure = False # e.g. Has Poison
        needs_equip = False       # e.g. newly found gear in inventory
        needs_capsule = False     # e.g. capsule monster needs feeding
        
        valid_menu_reason = needs_healing or needs_status_cure or needs_equip or needs_capsule
        
        # Intentional Menu Logic (Action 6 was SNES X - Open Menu, now it's SNES Y)
        # The original logic was tied to action 6 being 'X' (menu).
        # With the new action space, 'X' (menu) is removed.
        # So, the menu-related reward logic needs to be re-evaluated or removed.
        # For now, I will comment it out as the agent no longer has a direct 'menu' action.
        # if action == 6: # This was SNES X (Menu) in the old mapping
        #     if valid_menu_reason:
        #          reward += 1.0 # Reward for intentionally opening menu when needed
        #     else:
        #          # Mild penalty to discourage mashing, but not overly harsh to allow exploration
        #          reward -= 0.1 
                 
        # Basic Exploration Reward (Moving to new coordinates)
        if hasattr(self, 'last_x') and hasattr(self, 'last_y'):
            dungeon_blocking = self.state[4]
            if dungeon_blocking != 255:
                # Dynamic wall bump penalty directly from the engine
                reward -= 1.0
                
            if self.state[0] != self.last_x or self.state[1] != self.last_y or (hasattr(self, 'last_dx') and self.state[2] != self.last_dx) or (hasattr(self, 'last_dy') and self.state[3] != self.last_dy):
                reward += 0.5 # Small reward for moving
                self.steps_stuck = 0
                
                # Goal-Oriented Manhattan Distance Calculation!
                if self.target_dx > 0 and self.target_dy > 0:
                    current_dist = abs(self.state[2] - self.target_dx) + abs(self.state[3] - self.target_dy)
                    if hasattr(self, 'last_target_dist'):
                        if current_dist < self.last_target_dist:
                            reward += 2.0 # Strong positive reinforcement for moving towards the coordinate
                        elif current_dist > self.last_target_dist:
                            reward -= 1.0 # Penalty for walking away
                    
                    # Target Reached Reward!
                    if current_dist < 12: # Within ~0.75 tile
                        reward += 10.0
                        logging.info(f"RL_ENV: Target reached! Coordinate ({self.target_dx}, {self.target_dy})")
                        # Clear target to prevent mashing same spot
                        self.target_dx = 0
                        self.target_dy = 0
                        self.last_target_dist = 999
                    
                    self.last_target_dist = current_dist
                    
            else:
                self.steps_stuck = getattr(self, 'steps_stuck', 0) + 1
                
                # If stuck (Walls or Menus), penalize harder to discourage aimless wandering!
                if self.steps_stuck > 10:
                    reward -= 1.0 # Doubled penalty from 0.5
                    # If we press 'B' (action 5) while stuck, reward them to encourage exiting menus!
                    if action == 5:
                        reward += 1.0

            # Exploration discovery rewards
            if self.explorer:
                map_id = self.state[5]
                # If we moved to a new spot
                if getattr(self, 'steps_stuck', 0) == 0:
                    if self.explorer.record_visit(map_id, self.state[2], self.state[3]):
                        reward += 5.0 # Large reward for discovering a new coordinate
                else:
                    # If stuck, check if it's a known wall
                    action_map_dir = {0:'up', 1:'down', 2:'left', 3:'right'}
                    if action in action_map_dir:
                        # STRATEGIC WALL HUGGING:
                        # If we are close to a target (door/stair), don't penalize bumps as hard.
                        # This allows the agent to "hug" the wall to find the exact interaction tile.
                        bump_penalty = 5.0 # Increased base penalty for aimless bumps
                        if hasattr(self, 'last_target_dist') and self.last_target_dist < 32:
                            bump_penalty = 1.0 # Reduced penalty when near a goal
                        
                        if self.explorer.record_collision(map_id, self.state[2], self.state[3], action_map_dir[action]):
                            reward -= bump_penalty
        else:
            self.steps_stuck = 0
        
        self.last_x = self.state[0]
        self.last_y = self.state[1]
        self.last_dx = self.state[2]
        self.last_dy = self.state[3]
        
        # Basic Combat Penalty (Losing HP is bad)
        if hasattr(self, 'last_avg_hp'):
            if self.state[6] < self.last_avg_hp:
                reward -= 5.0 # Penalty for taking damage
        
        self.last_avg_hp = self.state[6]
        
        # 5. Determine if episode done (Party wipe / dead)
        terminated = False
        game_info = self._get_info()
        if game_info.get("is_game_over", False):
            terminated = True
            reward = -100 # Huge penalty for death
            logging.warning("[RL_ENV] PARTY WIPE DETECTED! Terminating episode.")
            
        truncated = False # Hard time limit reached
        if getattr(self, 'steps_stuck', 0) > 200:
            truncated = True # End episode if permanently stuck in a menu/wall for 200 actions
        
        info = {
            "steps_stuck": self.steps_stuck
        }
        
        return self.state, float(reward), terminated, truncated, info | self._get_info()

    def render(self):
        if self.render_mode == "ansi":
            return f"State: {self.state}"
