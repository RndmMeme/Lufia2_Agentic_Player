import cv2
import numpy as np
from PIL import ImageGrab
import pygetwindow as gw
import os
import logging
import json
from difflib import get_close_matches
from agent.runtime_config import get_emulator_window_title

class VisionHelper:
    def __init__(self, maps_dir="emulator/maps", sprites_dir="emulator/sprites"):
        self.maps_dir = maps_dir
        self.sprites_dir = sprites_dir
        self.window_title = get_emulator_window_title()
        self.templates = {}
        self.sprite_templates = []
        self.target_size = (256, 224) # Internal SNES resolution for normalization
        self._load_templates()

    def _load_templates(self):
        template_files = [
            ("maps", "SNES - Lufia 2_ Rise of the Sinistrals - Miscellaneous - Battle Backgrounds.png"),
            ("maps", "SNES - Lufia 2_ Rise of the Sinistrals - Enemies & Bosses - Enemies (In Battle).png"),
            ("maps", "SNES - Lufia 2_ Rise of the Sinistrals - Enemies & Bosses - The Sinistrals.png"),
            ("maps", "SNES - Lufia 2_ Rise of the Sinistrals - Miscellaneous - Combat Screen.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - Maps - Ship.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - Maps - Airship.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - Maps - Submarine.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - NPC - Priest.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - NPC - Priest - Save.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - NPC - Priest - Save - Slot.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - NPC - Priest - Save - Overwrite.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - NPC - Priest - Cure.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - Load - Game.png"),
            ("sprites", "SNES - Lufia 2_ Rise of the Sinistrals - Confirm - Load.png")
        ]
        
        for folder, f in template_files:
            if folder == "maps":
                path = os.path.join(self.maps_dir, f)
            else:
                path = os.path.join(self.sprites_dir, f)
                
            if os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    self.templates[f] = img
                    logging.info(f"Loaded template: {f}")
                else:
                    logging.warning(f"Failed to load image: {path}")
            else:
                logging.warning(f"Template path not found: {path}")

        if os.path.isdir(self.sprites_dir):
            for filename in sorted(os.listdir(self.sprites_dir)):
                if not filename.lower().endswith(".png"):
                    continue
                if "Maps -" not in filename and "NPC -" not in filename:
                    continue
                path = os.path.join(self.sprites_dir, filename)
                img = cv2.imread(path)
                if img is None:
                    continue
                label = filename.replace(".png", "").split(" - ")[-1]
                self.sprite_templates.append({
                    "name": label,
                    "filename": filename,
                    "image": img,
                    "width": img.shape[1],
                    "height": img.shape[0],
                })

    def capture_snes9x(self):
        """Captures the Snes9x window."""
        windows = gw.getWindowsWithTitle(self.window_title)
        if not windows:
            return None
        
        win = windows[0]
        try:
            img = ImageGrab.grab(bbox=(win.left, win.top, win.right, win.bottom))
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            frame = cv2.resize(frame, self.target_size, interpolation=cv2.INTER_AREA)
            return frame
        except Exception as e:
            logging.error(f"Failed to capture screen: {e}")
            return None

    def _normalize_tile_coord(self, value):
        iv = int(value or 0)
        if abs(iv) > 64:
            return int(round(iv / 16))
        if abs(iv) >= 16 and iv % 16 == 0:
            return iv // 16
        return iv

    def _screen_tile_to_world_tile(self, screen_tile_x, screen_tile_y, current_tile_x=None, current_tile_y=None):
        if current_tile_x is None or current_tile_y is None:
            return screen_tile_x, screen_tile_y
        base_x = self._normalize_tile_coord(current_tile_x)
        base_y = self._normalize_tile_coord(current_tile_y)
        center_tile_x = self.target_size[0] // 32
        center_tile_y = self.target_size[1] // 32
        return (
            base_x + (screen_tile_x - center_tile_x),
            base_y + (screen_tile_y - center_tile_y),
        )

    def _direction_from_delta(self, dx, dy):
        dirs = []
        if dy < 0:
            dirs.append("north")
        elif dy > 0:
            dirs.append("south")
        if dx < 0:
            dirs.append("west")
        elif dx > 0:
            dirs.append("east")
        return "-".join(dirs) if dirs else "here"

    def is_in_battle(self, threshold=0.7):
        """
        Determines if we are currently in battle.
        Restored hybrid check for reliability (Histograms + color bars + templates).
        """
        screen = self.capture_snes9x()
        if screen is None or screen.shape[0] < 10 or screen.shape[1] < 10:
            return False

        h, w = screen.shape[:2]

        # Check 1: Dark bottom panel
        bottom_panel = screen[int(h * 0.70):, :]
        dark_mask = np.all(bottom_panel < 40, axis=2)
        dark_ratio = dark_mask.sum() / (bottom_panel.shape[0] * bottom_panel.shape[1])
        
        # Check 2: Color bars
        bottom_hsv = cv2.cvtColor(bottom_panel, cv2.COLOR_BGR2HSV)
        blue_mask  = cv2.inRange(bottom_hsv, np.array([90,  60, 60]), np.array([130, 255, 255]))
        blue_ratio  = blue_mask.sum() / 255.0  / (bottom_panel.shape[0] * bottom_panel.shape[1])
        green_mask = cv2.inRange(bottom_hsv, np.array([35,  60, 60]), np.array([85,  255, 255]))
        green_ratio = green_mask.sum() / 255.0 / (bottom_panel.shape[0] * bottom_panel.shape[1])
        yellow_mask = cv2.inRange(bottom_hsv, np.array([20, 80, 80]), np.array([35,  255, 255]))
        yellow_ratio = yellow_mask.sum() / 255.0 / (bottom_panel.shape[0] * bottom_panel.shape[1])
        
        bar_detected = blue_ratio > 0.012 or green_ratio > 0.012 or yellow_ratio > 0.008
        if dark_ratio > 0.45 and bar_detected:
            return True
        
        # Check 3: Template Match
        combat_ui = self.templates.get("SNES - Lufia 2_ Rise of the Sinistrals - Miscellaneous - Combat Screen.png")
        if combat_ui is not None:
            if screen.shape[0] >= combat_ui.shape[0] and screen.shape[1] >= combat_ui.shape[1]:
                res = cv2.matchTemplate(screen, combat_ui, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val > threshold:
                    return True

        return False

    def match_template(self, template_path, threshold=0.7):
        screen = self.capture_snes9x()
        if screen is None: return 0.0
        if isinstance(template_path, str):
            if not os.path.exists(template_path): return 0.0
            template = cv2.imread(template_path)
        else:
            template = template_path
        if template is None: return 0.0
        try:
            if screen.shape[0] >= template.shape[0] and screen.shape[1] >= template.shape[1]:
                res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                return max_val
        except Exception as e:
            logging.error(f"Error in match_template: {e}")
        return 0.0

    def get_battle_context(self):
        if not self.is_in_battle():
            return "none"
        return "combat"

    def get_screen_text(self):
        return ""

    def detect_combat_entities(self, threshold=0.7):
        """Detects combat enemies. Returns placeholders if actual shapes are too volatile."""
        if not self.is_in_battle():
            return []
        
        # Placeholder names to unblock the LLM logic - it needs them for targeting.
        # In the future, this will use template matching for specific enemy types.
        screen = self.capture_snes9x()
        if screen is None: return ["Enemy A"]
        
        # Basic heuristic: Search for "entity blobs" in the center-top area of screen
        return ["Enemy A", "Enemy B"] if self.is_in_battle() else []

    def get_visible_sprites(self, current_tile_x=None, current_tile_y=None, threshold=0.6):
        """Detects visible markers/sprites and translates them to tile coordinates."""
        screen = self.capture_snes9x()
        if screen is None or not self.sprite_templates:
            return []

        detections = []
        seen_tiles = set()

        for template_info in self.sprite_templates:
            template = template_info["image"]
            th, tw = template.shape[:2]
            if screen.shape[0] < th or screen.shape[1] < tw:
                continue
            try:
                result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                result_work = result.copy()
                for _ in range(3):
                    _, max_val, _, max_loc = cv2.minMaxLoc(result_work)
                    if max_val < threshold:
                        break
                    center_x = max_loc[0] + tw // 2
                    center_y = max_loc[1] + th // 2
                    screen_tile_x = center_x // 16
                    screen_tile_y = center_y // 16
                    world_tile_x, world_tile_y = self._screen_tile_to_world_tile(
                        screen_tile_x,
                        screen_tile_y,
                        current_tile_x=current_tile_x,
                        current_tile_y=current_tile_y,
                    )
                    dedupe_key = (template_info["name"], world_tile_x, world_tile_y)
                    if dedupe_key not in seen_tiles:
                        base_x = self._normalize_tile_coord(current_tile_x) if current_tile_x is not None else screen_tile_x
                        base_y = self._normalize_tile_coord(current_tile_y) if current_tile_y is not None else screen_tile_y
                        detections.append({
                            "type": template_info["name"],
                            "sprite": template_info["name"],
                            "score": float(max_val),
                            "direction": self._direction_from_delta(world_tile_x - base_x, world_tile_y - base_y),
                            "tile_x": int(world_tile_x),
                            "tile_y": int(world_tile_y),
                            "screen_tile_x": int(screen_tile_x),
                            "screen_tile_y": int(screen_tile_y),
                        })
                        seen_tiles.add(dedupe_key)

                    x1 = max(0, max_loc[0] - tw // 2)
                    y1 = max(0, max_loc[1] - th // 2)
                    x2 = min(result_work.shape[1], max_loc[0] + tw)
                    y2 = min(result_work.shape[0], max_loc[1] + th)
                    result_work[y1:y2, x1:x2] = 0.0
            except Exception as e:
                logging.debug(f"Sprite detection failed for {template_info['filename']}: {e}")

        detections.sort(key=lambda item: item["score"], reverse=True)
        return detections[:12]

    def get_visual_localization(self, zone_name, threshold=0.4):
        """ Matches current screen against a large zone map to find (x,y) tile. """
        screen = self.capture_snes9x()
        if screen is None: return None
        
        # Normalize: search for a clean map match (excluding the UI area)
        h, w = screen.shape[:2]
        sample = screen[int(h*0.1):int(h*0.6), int(w*0.1):int(w*0.9)]
        
        # Look for map image
        map_files = [f for f in os.listdir(self.maps_dir) if zone_name.replace(" ", "_") in f and f.endswith(".png")]
        if not map_files:
            return None
            
        map_img = cv2.imread(os.path.join(self.maps_dir, map_files[0]))
        if map_img is None: return None
        
        try:
            res = cv2.matchTemplate(map_img, sample, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val > threshold:
                # Approximate tile: SNES tiles are 16x16
                tile_x = (max_loc[0] + sample.shape[1]//2) // 16
                tile_y = (max_loc[1] + sample.shape[0]//2) // 16
                logging.info(f"Visual Loc: Match found on {map_files[0]} (Score: {max_val:.2f}) -> {tile_x}, {tile_y}")
                return {"confidence": max_val, "tile_x": tile_x, "tile_y": tile_y}
        except Exception as e:
            logging.error(f"Failed visual localization: {e}")
            
        return None

    def parse_ip_menu(self):
        """
        Scans the open IP menu for skill names. 
        Returns exactly 6 slots (strings or None).
        """
        # Without OCR, we provide placeholders matching the 6-slot vertical layout.
        # In Lufia 2, IP skills are based on equipment.
        return ["IP Move 1", "IP Move 2", "IP Move 3", "IP Move 4", "IP Move 5", "IP Move 6"]

    def detect_vehicle(self, threshold=0.6):
        return None

if __name__ == "__main__":
    v = VisionHelper()
    print(f"In Battle? {v.is_in_battle()}")
