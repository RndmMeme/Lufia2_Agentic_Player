import json
import logging
import os


STATIC_WALL_SPRITES = {
    "Castle_Door_Closed", "Mountain_Door_Closed", "Door_Locked"
}

PUZZLE_SPRITES = {
    "lever", "pillar", "weight_tile", "floor_switch",
    "vines", "jumpable_edge_L", "jumpable_edge_R", "Crate"
}

PUZZLE_STUCK_CYCLES = 3
PUZZLE_AUTO_PULL_CYCLES = 5
STUCK_AREA_THRESHOLD = 9
TILE_SIZE = 16
DIRS = {
    "north": (0, -1),
    "south": (0, 1),
    "west": (-1, 0),
    "east": (1, 0),
}
OPPOSITE = {"north": "south", "south": "north", "west": "east", "east": "west"}


class ExplorationManager:
    LANDMARK_LABELS = {
        "Door_Closed": ("Dungeon Door (Closed)", False),
        "Door_Open": ("Dungeon Door (Open)", False),
        "Door_Locked": ("Locked Door", False),
        "Castle_Door_Closed": ("Castle Gate (Closed)", False),
        "Castle_Door_Open": ("Castle Gate (Open)", False),
        "Mountain_Door_Closed": ("Mountain Door (Closed)", False),
        "Mountain_Door_Open": ("Mountain Door (Open)", False),
        "Stairs_Up_L": ("Staircase (Up)", False),
        "Stairs_Up_R": ("Staircase (Up)", False),
        "Stairs_Down_L": ("Staircase (Down)", False),
        "Stairs_Down_R": ("Staircase (Down)", False),
        "Mountain_Stairs": ("Mountain Staircase", False),
        "Capsule_Shrine_Stairs": ("Capsule Shrine Stairs", False),
        "ladder": ("Ladder", False),
        "Red_Chest_Closed": ("Red Chest (Unopened)", False),
        "Red_Chest_Open": ("Red Chest (Opened)", False),
        "Blue_Chest_Closed": ("Blue Chest (Unopened)", False),
        "Blue_Chest_Open": ("Blue Chest (Opened)", False),
        "Teleport_Active": ("Teleport Tile (Active)", False),
        "Teleport_Inactive": ("Teleport Tile (Inactive)", False),
        "House_Exit_(Interior)": ("Room Exit", False),
        "Hookable_Stump": ("Hookable Stump (Use Hook)", False),
        "lever": ("Lever / Switch", True),
        "pillar": ("Pushable Pillar", True),
        "weight_tile": ("Pressure Plate", True),
        "floor_switch": ("Floor Switch", True),
        "vines": ("Climbable Vines", True),
        "jumpable_edge_L": ("Jumpable Ledge", True),
        "jumpable_edge_R": ("Jumpable Ledge", True),
        "Crate": ("Pushable Crate", True),
        "pot": ("Pot (Check for items)", False),
        "Bush": ("Bush (Cuttable)", False),
        "INN": ("Inn", False),
        "Shop": ("Shop", False),
        "Statue_Horse_L": ("Horse Statue", False),
        "Statue_Horse_R": ("Horse Statue", False),
    }

    def __init__(self, data_file="data/exploration_memory.json"):
        self.data_file = data_file
        self.memory = {}
        self._session_walls = {}
        self._defeated_encounters = {}
        self._stuck_cycles = {}
        self._recent_positions = {}
        self.load_memory()

    def _empty_map_memory(self):
        return {
            "heatmap": {},
            "walls": [],
            "landmarks": [],
            "tiles": {},
            "route_memory": {
                "junctions": {},
                "dead_ends": [],
                "unfinished_branches": [],
                "segments": {},
                "current_segment": None,
            },
            "meta": {
                "coord_mode": "tile16",
                "tile_size": TILE_SIZE,
            },
        }

    def load_memory(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
                logging.info(f"Loaded exploration memory for {len(self.memory)} maps.")
            except Exception as e:
                logging.error(f"Error loading exploration memory: {e}")
                self.memory = {}

    def save_memory(self):
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving exploration memory: {e}")

    def _normalize_axis(self, value):
        iv = int(value or 0)
        if abs(iv) > 64:
            return int(round(iv / TILE_SIZE))
        if abs(iv) >= TILE_SIZE and iv % TILE_SIZE == 0:
            return iv // TILE_SIZE
        return iv

    def _normalize_point(self, x, y):
        return (self._normalize_axis(x), self._normalize_axis(y))

    def _tile_key(self, x, y):
        return f"{int(x)},{int(y)}"

    def _parse_tile_key(self, key):
        sx, sy = str(key).split(",")
        return int(sx), int(sy)

    def _ensure_tile(self, mid, x, y):
        key = self._tile_key(x, y)
        tiles = self.memory[mid]["tiles"]
        if key not in tiles:
            tiles[key] = {
                "visited": False,
                "heat": 0,
                "wall_dirs": [],
                "landmarks": [],
                "puzzle": False,
                "dead_end": False,
                "junction": False,
                "segment_id": None,
            }
        return tiles[key]

    def _migrate_map(self, mid):
        current = self.memory.get(mid, {})
        merged = self._empty_map_memory()
        current_heatmap = dict((current.get("heatmap", {}) or {})) if isinstance(current, dict) else {}
        current_walls = list((current.get("walls", []) or [])) if isinstance(current, dict) else []
        current_landmarks = list((current.get("landmarks", []) or [])) if isinstance(current, dict) else []
        current_route_memory = dict((current.get("route_memory", {}) or {})) if isinstance(current, dict) else {}
        current_meta = dict((current.get("meta", {}) or {})) if isinstance(current, dict) else {}

        heatmap = {}
        for raw_key, raw_heat in current_heatmap.items():
            try:
                x, y = self._parse_tile_key(raw_key)
                tx, ty = self._normalize_point(x, y)
                key = self._tile_key(tx, ty)
                heatmap[key] = heatmap.get(key, 0) + int(raw_heat or 0)
            except Exception:
                continue

        self.memory[mid] = merged
        self.memory[mid]["route_memory"].update(current_route_memory)
        self.memory[mid]["meta"].update(current_meta)

        for key, heat in heatmap.items():
            self.memory[mid]["heatmap"][key] = heat
            tx, ty = self._parse_tile_key(key)
            tile = self._ensure_tile(mid, tx, ty)
            tile["visited"] = True
            tile["heat"] = self.memory[mid]["heatmap"][key]

        migrated_walls = []
        for entry in current_walls:
            if not isinstance(entry, dict):
                continue
            tx, ty = self._normalize_point(entry.get("x", 0), entry.get("y", 0))
            direction = str(entry.get("dir", "")).lower()
            if direction not in DIRS:
                continue
            wall = {"x": tx, "y": ty, "dir": direction}
            if wall not in migrated_walls:
                migrated_walls.append(wall)
                self._ensure_tile(mid, tx, ty)["wall_dirs"] = sorted(
                    set(self._ensure_tile(mid, tx, ty).get("wall_dirs", []) + [direction])
                )
        self.memory[mid]["walls"] = migrated_walls

        migrated_landmarks = []
        for entry in current_landmarks:
            if not isinstance(entry, dict):
                continue
            tx, ty = self._normalize_point(entry.get("x", 0), entry.get("y", 0))
            sprite_type = entry.get("type")
            lm = {"x": tx, "y": ty, "type": sprite_type}
            if lm not in migrated_landmarks:
                migrated_landmarks.append(lm)
                tile = self._ensure_tile(mid, tx, ty)
                tile["landmarks"] = sorted(set(tile.get("landmarks", []) + [sprite_type]))
                tile["puzzle"] = tile["puzzle"] or sprite_type in PUZZLE_SPRITES
        self.memory[mid]["landmarks"] = migrated_landmarks

    def _ensure_map(self, map_id):
        mid = str(map_id)
        if mid not in self.memory:
            self.memory[mid] = self._empty_map_memory()
        self._migrate_map(mid)
        if mid not in self._session_walls:
            self._session_walls[mid] = []
        if mid not in self._defeated_encounters:
            self._defeated_encounters[mid] = []
        if mid not in self._stuck_cycles:
            self._stuck_cycles[mid] = 0
        if mid not in self._recent_positions:
            self._recent_positions[mid] = []
        return mid

    def _visited_tiles(self, map_id):
        mid = self._ensure_map(map_id)
        visited = set()
        for key, tile in (self.memory[mid].get("tiles", {}) or {}).items():
            if tile.get("visited") or tile.get("heat", 0) > 0:
                visited.add(self._parse_tile_key(key))
        if not visited:
            for key in (self.memory[mid].get("heatmap", {}) or {}):
                try:
                    visited.add(self._parse_tile_key(key))
                except Exception:
                    continue
        return visited

    def _neighbor_coords(self, x, y):
        ix, iy = int(x), int(y)
        return {direction: (ix + dx, iy + dy) for direction, (dx, dy) in DIRS.items()}

    def _get_all_walls(self, map_id):
        mid = self._ensure_map(map_id)
        return list(self.memory[mid]["walls"]) + list(self._session_walls.get(mid, []))

    def _is_walled(self, map_id, x, y, direction, wall_list=None):
        tx, ty = self._normalize_point(x, y)
        if wall_list is None:
            wall_list = self._get_all_walls(map_id)
        return {"x": int(tx), "y": int(ty), "dir": direction} in wall_list

    def _tile_has_landmark(self, map_id, x, y):
        mid = self._ensure_map(map_id)
        tile = self.memory[mid]["tiles"].get(self._tile_key(x, y), {})
        return bool(tile.get("landmarks"))

    def _tile_is_puzzle(self, map_id, x, y):
        mid = self._ensure_map(map_id)
        tile = self.memory[mid]["tiles"].get(self._tile_key(x, y), {})
        return bool(tile.get("puzzle"))

    def _frontier_dirs_for_tile(self, map_id, x, y, visited_tiles=None, wall_list=None):
        visited_tiles = visited_tiles or self._visited_tiles(map_id)
        wall_list = wall_list or self._get_all_walls(map_id)
        frontier_dirs = []
        for direction, (nx, ny) in self._neighbor_coords(x, y).items():
            if self._is_walled(map_id, x, y, direction, wall_list):
                continue
            if (nx, ny) not in visited_tiles:
                frontier_dirs.append(direction)
        return frontier_dirs

    def _is_frontier_tile(self, map_id, tx, ty, visited_tiles=None, wall_list=None):
        visited_tiles = visited_tiles or self._visited_tiles(map_id)
        wall_list = wall_list or self._get_all_walls(map_id)
        tile = (int(tx), int(ty))
        if tile in visited_tiles:
            return False
        for direction, (nx, ny) in self._neighbor_coords(tile[0], tile[1]).items():
            if (nx, ny) in visited_tiles and not self._is_walled(map_id, nx, ny, OPPOSITE[direction], wall_list):
                return True
        return False

    def _compute_segments(self, map_id, visited_tiles, wall_list):
        remaining = set(visited_tiles)
        segments = {}
        tile_to_segment = {}
        seg_idx = 1
        while remaining:
            start = remaining.pop()
            queue = [start]
            component = {start}
            while queue:
                cx, cy = queue.pop(0)
                for direction, (nx, ny) in self._neighbor_coords(cx, cy).items():
                    if (nx, ny) not in remaining:
                        continue
                    if self._is_walled(map_id, cx, cy, direction, wall_list):
                        continue
                    remaining.remove((nx, ny))
                    component.add((nx, ny))
                    queue.append((nx, ny))
            xs = [p[0] for p in component]
            ys = [p[1] for p in component]
            segment_id = f"segment_{seg_idx}"
            seg_idx += 1
            segments[segment_id] = {
                "tile_count": len(component),
                "bbox": {
                    "min_x": min(xs),
                    "max_x": max(xs),
                    "min_y": min(ys),
                    "max_y": max(ys),
                },
            }
            for tile in component:
                tile_to_segment[tile] = segment_id
        return segments, tile_to_segment

    def _build_route_memory(self, map_id, current_x, current_y):
        mid = self._ensure_map(map_id)
        visited_tiles = self._visited_tiles(map_id)
        wall_list = self._get_all_walls(map_id)
        segments, tile_to_segment = self._compute_segments(map_id, visited_tiles, wall_list)
        junctions = {}
        dead_ends = []
        unfinished_branches = []

        for tile in visited_tiles:
            tx, ty = tile
            open_dirs = []
            visited_dirs = []
            frontier_dirs = []
            landmark_dirs = []

            for direction, (nx, ny) in self._neighbor_coords(tx, ty).items():
                if self._is_walled(map_id, tx, ty, direction, wall_list):
                    continue
                open_dirs.append(direction)
                if (nx, ny) in visited_tiles:
                    visited_dirs.append(direction)
                else:
                    frontier_dirs.append(direction)
                if self._tile_has_landmark(map_id, nx, ny):
                    landmark_dirs.append(direction)

            key = self._tile_key(tx, ty)
            tile_entry = self._ensure_tile(mid, tx, ty)
            tile_entry["segment_id"] = tile_to_segment.get(tile)
            tile_entry["junction"] = False
            tile_entry["dead_end"] = False

            if len(visited_dirs) <= 1 and not frontier_dirs:
                dead_ends.append({"x": tx, "y": ty})
                tile_entry["dead_end"] = True

            if len(visited_dirs) >= 3 or len(frontier_dirs) >= 2 or landmark_dirs:
                junctions[key] = {
                    "x": tx,
                    "y": ty,
                    "open_dirs": open_dirs,
                    "frontier_dirs": frontier_dirs,
                    "landmark_dirs": landmark_dirs,
                    "segment_id": tile_to_segment.get(tile),
                }
                tile_entry["junction"] = True
                for direction in frontier_dirs:
                    unfinished_branches.append({
                        "from_x": tx,
                        "from_y": ty,
                        "direction": direction,
                        "segment_id": tile_to_segment.get(tile),
                    })

        current_segment = tile_to_segment.get((current_x, current_y))
        route_memory = {
            "junctions": junctions,
            "dead_ends": dead_ends,
            "unfinished_branches": unfinished_branches,
            "segments": segments,
            "current_segment": current_segment,
        }
        self.memory[mid]["route_memory"] = route_memory
        return route_memory

    def record_visit(self, map_id, x, y):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        key = self._tile_key(tx, ty)
        was_new = key not in self.memory[mid]["heatmap"]
        self.memory[mid]["heatmap"][key] = self.memory[mid]["heatmap"].get(key, 0) + 1
        tile = self._ensure_tile(mid, tx, ty)
        tile["visited"] = True
        tile["heat"] = self.memory[mid]["heatmap"][key]
        recent = self._recent_positions[mid]
        recent.append((tx, ty))
        if len(recent) > 24:
            recent.pop(0)
        return was_new

    def decay_heatmap(self, map_id):
        mid = self._ensure_map(map_id)
        for key in list(self.memory[mid]["heatmap"].keys()):
            self.memory[mid]["heatmap"][key] = max(1, int(self.memory[mid]["heatmap"][key]) - 1)
            tx, ty = self._parse_tile_key(key)
            self._ensure_tile(mid, tx, ty)["heat"] = self.memory[mid]["heatmap"][key]

    def get_tile_heat(self, map_id, x, y):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        return int(self.memory[mid]["heatmap"].get(self._tile_key(tx, ty), 0))

    def record_attempt(self, map_id, x, y, direction, sprite_type=None):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        entry = {"x": tx, "y": ty, "dir": direction}

        if entry in self._defeated_encounters.get(mid, []):
            logging.debug(
                f"Skipping wall inference at ({tx},{ty}) dir={direction}; encounter was previously defeated here this session."
            )
            return

        if sprite_type in PUZZLE_SPRITES:
            tile = self._ensure_tile(mid, tx, ty)
            tile["puzzle"] = True

        is_static = sprite_type in STATIC_WALL_SPRITES if sprite_type else False
        if is_static:
            if entry not in self.memory[mid]["walls"]:
                self.memory[mid]["walls"].append(entry)
            tile = self._ensure_tile(mid, tx, ty)
            tile["wall_dirs"] = sorted(set(tile.get("wall_dirs", []) + [direction]))
        else:
            if entry not in self._session_walls[mid]:
                self._session_walls[mid].append(entry)

    def clear_attempt(self, map_id, x, y, direction):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        entry = {"x": tx, "y": ty, "dir": direction}
        if entry in self._session_walls[mid]:
            self._session_walls[mid].remove(entry)

    def record_defeated_encounter(self, map_id, x, y, direction):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        entry = {"x": tx, "y": ty, "dir": direction}
        if entry not in self._defeated_encounters[mid]:
            self._defeated_encounters[mid].append(entry)
        self.clear_attempt(map_id, tx, ty, direction)

    def record_landmark(self, map_id, x, y, sprite_type):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        entry = {"x": tx, "y": ty, "type": sprite_type}
        if entry not in self.memory[mid]["landmarks"]:
            self.memory[mid]["landmarks"].append(entry)
            label, is_puzzle = self.LANDMARK_LABELS.get(sprite_type, (sprite_type, False))
            logging.info(f"Landmark registered: {label} at ({tx},{ty}) [puzzle={is_puzzle}]")
        tile = self._ensure_tile(mid, tx, ty)
        tile["landmarks"] = sorted(set(tile.get("landmarks", []) + [sprite_type]))
        tile["puzzle"] = tile["puzzle"] or sprite_type in PUZZLE_SPRITES

    def get_landmarks(self, map_id):
        mid = self._ensure_map(map_id)
        return self.memory[mid].get("landmarks", [])

    def get_nearest_landmark(self, map_id, x, y, sprite_type):
        tx, ty = self._normalize_point(x, y)
        landmarks = [l for l in self.get_landmarks(map_id) if l["type"] == sprite_type]
        if not landmarks:
            return None
        return min(landmarks, key=lambda l: abs(int(l["x"]) - tx) + abs(int(l["y"]) - ty))

    def _recent_trail_summary(self, map_id, max_points=8):
        mid = self._ensure_map(map_id)
        recent = self._recent_positions.get(mid, [])
        if not recent:
            return []
        unique = []
        for pos in recent:
            if not unique or unique[-1] != pos:
                unique.append(pos)
        tail = unique[-max_points:]
        return [{"x": int(px), "y": int(py)} for px, py in tail]

    def _immediate_backtrack_direction(self, map_id):
        mid = self._ensure_map(map_id)
        recent = self._recent_positions.get(mid, [])
        unique = []
        for pos in recent:
            if not unique or unique[-1] != pos:
                unique.append(pos)
        if len(unique) < 2:
            return None
        curr_x, curr_y = unique[-1]
        prev_x, prev_y = unique[-2]
        dx = prev_x - curr_x
        dy = prev_y - curr_y
        for direction, (mx, my) in DIRS.items():
            if (dx, dy) == (mx, my):
                return direction
        return None

    def _landmark_bias(self, map_id, x, y, direction, nearby_landmarks=None):
        if nearby_landmarks is None:
            nearby_landmarks = self.get_landmarks(map_id)
        tx, ty = int(x), int(y)
        nx, ny = self._neighbor_coords(tx, ty)[direction]
        score = 0
        for landmark in nearby_landmarks:
            lx, ly = int(landmark["x"]), int(landmark["y"])
            current_dist = abs(lx - tx) + abs(ly - ty)
            next_dist = abs(lx - nx) + abs(ly - ny)
            if next_dist >= current_dist:
                continue
            label, is_puzzle = self.LANDMARK_LABELS.get(landmark["type"], (landmark["type"], False))
            if "Staircase" in label or "Door" in label or "Exit" in label:
                score += 3
            elif is_puzzle:
                score += 1
            else:
                score += 2
        return score

    def _rank_frontier_directions(self, map_id, x, y):
        tx, ty = self._normalize_point(x, y)
        visited_tiles = self._visited_tiles(map_id)
        wall_list = self._get_all_walls(map_id)
        route_memory = self._build_route_memory(map_id, tx, ty)
        dead_ends = {(int(d["x"]), int(d["y"])) for d in route_memory.get("dead_ends", [])}
        recent_tail = self._recent_trail_summary(map_id, max_points=8)
        recent_positions = [(entry["x"], entry["y"]) for entry in recent_tail]
        backtrack_dir = self._immediate_backtrack_direction(map_id)
        nearby_landmarks = self.get_landmarks(map_id)

        scores = {}
        neighbors = self._neighbor_coords(tx, ty)
        for direction, (nx, ny) in neighbors.items():
            if self._is_walled(map_id, tx, ty, direction, wall_list):
                continue
            score = 0
            if (nx, ny) not in visited_tiles:
                score += 8
            score -= self.get_tile_heat(map_id, nx, ny)

            frontier_bonus = 0
            for sx in range(nx - 2, nx + 3):
                for sy in range(ny - 2, ny + 3):
                    if abs(sx - nx) + abs(sy - ny) > 3:
                        continue
                    if self._is_frontier_tile(map_id, sx, sy, visited_tiles, wall_list):
                        frontier_bonus += 2
            score += frontier_bonus

            if (nx, ny) in recent_positions:
                closeness_penalty = len(recent_positions) - recent_positions.index((nx, ny))
                score -= min(7, 2 + closeness_penalty)
            if backtrack_dir and direction == backtrack_dir:
                score -= 5
            if (nx, ny) in dead_ends and not self._frontier_dirs_for_tile(map_id, nx, ny, visited_tiles, wall_list):
                score -= 3
            score += self._landmark_bias(map_id, tx, ty, direction, nearby_landmarks)
            scores[direction] = score

        ranked = [direction for direction, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]
        return scores, ranked

    def get_least_visited_direction(self, map_id, x, y):
        tx, ty = self._normalize_point(x, y)
        neighbors = self._neighbor_coords(tx, ty)
        wall_list = self._get_all_walls(map_id)
        available = {
            direction: coords
            for direction, coords in neighbors.items()
            if not self._is_walled(map_id, tx, ty, direction, wall_list)
        }
        if not available:
            return None
        heats = {direction: self.get_tile_heat(map_id, nx, ny) for direction, (nx, ny) in available.items()}
        return min(heats, key=heats.get)

    def get_preferred_frontier_direction(self, map_id, x, y):
        _, ranked = self._rank_frontier_directions(map_id, x, y)
        if ranked:
            return ranked[0]
        return self.get_least_visited_direction(map_id, x, y)

    def _build_local_minimap(self, map_id, x, y, radius=4):
        tx, ty = self._normalize_point(x, y)
        visited_tiles = self._visited_tiles(map_id)
        wall_list = self._get_all_walls(map_id)
        landmark_tiles = {(int(l["x"]), int(l["y"])) for l in self.get_landmarks(map_id)}
        rows = []
        for py in range(ty - radius, ty + radius + 1):
            chars = []
            for px in range(tx - radius, tx + radius + 1):
                tile = (px, py)
                if tile == (tx, ty):
                    chars.append("C")
                elif tile in landmark_tiles:
                    chars.append("L")
                elif tile in visited_tiles:
                    chars.append(".")
                elif self._is_frontier_tile(map_id, px, py, visited_tiles, wall_list):
                    chars.append("?")
                else:
                    chars.append(" ")
            rows.append("".join(chars))
        return "\n".join(rows)

    def _frontier_summary(self, map_id, x, y, limit=3):
        tx, ty = self._normalize_point(x, y)
        scores, ranked = self._rank_frontier_directions(map_id, tx, ty)
        visited_tiles = self._visited_tiles(map_id)
        route_memory = self.memory[self._ensure_map(map_id)].get("route_memory", {})
        unfinished = route_memory.get("unfinished_branches", [])
        dead_ends = {(int(d["x"]), int(d["y"])) for d in route_memory.get("dead_ends", [])}
        summary = []
        for direction in ranked[:limit]:
            nx, ny = self._neighbor_coords(tx, ty)[direction]
            reasons = []
            if (nx, ny) not in visited_tiles:
                reasons.append("fresh tile")
            else:
                reasons.append(f"heat {self.get_tile_heat(map_id, nx, ny)}")
            nearby_frontiers = 0
            for sx in range(nx - 2, nx + 3):
                for sy in range(ny - 2, ny + 3):
                    if abs(sx - nx) + abs(sy - ny) > 3:
                        continue
                    if self._is_frontier_tile(map_id, sx, sy, visited_tiles):
                        nearby_frontiers += 1
            if nearby_frontiers:
                reasons.append(f"{nearby_frontiers} frontier tiles nearby")
            if any(b["direction"] == direction and b["from_x"] == tx and b["from_y"] == ty for b in unfinished):
                reasons.append("unfinished branch")
            if (nx, ny) in dead_ends:
                reasons.append("known dead end")
            landmark_bias = self._landmark_bias(map_id, tx, ty, direction)
            if landmark_bias > 0:
                reasons.append("moves toward landmark")
            summary.append({
                "direction": direction,
                "score": scores.get(direction, 0),
                "reasons": reasons,
            })
        return summary

    def update_stuck_state(self, map_id):
        mid = self._ensure_map(map_id)
        recent = self._recent_positions.get(mid, [])
        if len(recent) < 5:
            return 0, False, False
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        bbox_area = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        if bbox_area <= STUCK_AREA_THRESHOLD:
            self._stuck_cycles[mid] = self._stuck_cycles.get(mid, 0) + 1
        else:
            self._stuck_cycles[mid] = 0
        cycles = self._stuck_cycles[mid]
        return cycles, cycles >= PUZZLE_STUCK_CYCLES, cycles >= PUZZLE_AUTO_PULL_CYCLES

    def reset_stuck(self, map_id):
        mid = self._ensure_map(map_id)
        self._stuck_cycles[mid] = 0
        self._recent_positions[mid] = []
        self._session_walls[mid] = []

    def get_context_for_llm(self, map_id, x, y):
        mid = self._ensure_map(map_id)
        tx, ty = self._normalize_point(x, y)
        visited_count = len(self._visited_tiles(map_id))
        current_heat = self.get_tile_heat(map_id, tx, ty)
        route_memory = self._build_route_memory(map_id, tx, ty)
        best_dir = self.get_preferred_frontier_direction(map_id, tx, ty)
        frontier_scores, ranked_frontiers = self._rank_frontier_directions(map_id, tx, ty)
        frontier_summary = self._frontier_summary(map_id, tx, ty)
        recent_trail = self._recent_trail_summary(map_id)
        backtrack_dir = self._immediate_backtrack_direction(map_id)
        minimap = self._build_local_minimap(map_id, tx, ty)
        blocked_dirs = [d for d in DIRS if self._is_walled(map_id, tx, ty, d)]

        nearby_landmarks = []
        for lm in self.get_landmarks(map_id):
            lx, ly = int(lm["x"]), int(lm["y"])
            dist = abs(lx - tx) + abs(ly - ty)
            if dist <= 15:
                label, is_puzzle = self.LANDMARK_LABELS.get(lm["type"], (lm["type"], False))
                dx = lx - tx
                dy = ly - ty
                dirs = []
                if dy < 0:
                    dirs.append("N")
                elif dy > 0:
                    dirs.append("S")
                if dx > 0:
                    dirs.append("E")
                elif dx < 0:
                    dirs.append("W")
                nearby_landmarks.append({
                    "label": label,
                    "direction": "".join(dirs) or "here",
                    "dist_tiles": dist,
                    "is_puzzle_element": is_puzzle,
                })
        nearby_landmarks.sort(key=lambda item: item["dist_tiles"])
        has_puzzle_elements = any(item["is_puzzle_element"] for item in nearby_landmarks)
        stuck_cycles, is_stuck, should_auto_pull = self.update_stuck_state(map_id)

        return {
            "tile": {"x": tx, "y": ty},
            "tiles_explored": visited_count,
            "current_tile_heat": current_heat,
            "best_unexplored_direction": best_dir,
            "frontier_scores": frontier_scores,
            "ranked_frontiers": ranked_frontiers,
            "frontier_summary": frontier_summary,
            "blocked_directions": blocked_dirs,
            "recent_trail": recent_trail,
            "immediate_backtrack_direction": backtrack_dir,
            "local_minimap": minimap,
            "route_memory": {
                "current_segment": route_memory.get("current_segment"),
                "segment_count": len(route_memory.get("segments", {})),
                "junction_count": len(route_memory.get("junctions", {})),
                "dead_end_count": len(route_memory.get("dead_ends", [])),
                "unfinished_branch_count": len(route_memory.get("unfinished_branches", [])),
            },
            "exploration_policy": "Prefer promising frontier and useful landmarks. Full 100% exploration is not required unless progress stalls.",
            "nearby_landmarks": nearby_landmarks,
            "has_puzzle_elements": has_puzzle_elements,
            "stuck_cycles": stuck_cycles,
            "puzzle_hint_active": is_stuck,
            "auto_pull_puzzle": should_auto_pull,
            "navigation_mode": "puzzle_solve" if (has_puzzle_elements and is_stuck) else "explore",
        }

    def get_discovery_stats(self, map_id):
        mid = self._ensure_map(map_id)
        return {
            "visited_count": len(self._visited_tiles(map_id)),
            "walls_detected": len(self.memory[mid].get("walls", [])),
            "landmarks": len(self.memory[mid].get("landmarks", [])),
        }
