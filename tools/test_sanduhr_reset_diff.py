"""Sanduhr-Reset-Test: Raum zurücksetzen, Figur an Schussstelle, Pfeil abfeuern, Diff prüfen.

Ablauf:
1. Position prüfen: Figur muss bei (28,24) sein, Blickrichtung West, Pfeil ausgewählt
2. Sanduhr-Reset: Select + Up + A (Brücke wird deaktiviert)
3. Post-Reset-Dump: Brücke sollte deaktiviert sein (0x02)
4. Figur an Schussstelle bringen (28,24), Blickrichtung West
5. Pfeil schießen (use_tool)
6. Post-Arrow-Dump: Brücke sollte aktiviert sein (0x00)
7. Diff: 0x02 -> 0x00
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.mesen_controller import MesenController
from agent.config import load_config

def tile_addr(x: int, y: int) -> int:
    return 0x4000 + x + y * 0x3A

BRIDGE_TILES = [
    (24, 26),
    (24, 27),
    (24, 28),
]

def dump_bridge(controller: MesenController, label: str) -> dict:
    tiles = {}
    for x, y in BRIDGE_TILES:
        addr = tile_addr(x, y)
        value = controller.bridge.read(addr, 1)[0]
        tiles[f"({x},{y})"] = {"addr": f"0x{addr:04X}", "value": f"0x{value:02X}"}
    print(f"=== {label} ===")
    for pos, info in tiles.items():
        print(f"  {pos} @ {info['addr']} = {info['value']}")
    return tiles

def get_state(controller: MesenController) -> dict:
    obs = controller.observe()
    return {
        "x": obs.game.x,
        "y": obs.game.y,
        "direction": obs.game.direction,
        "map_id": obs.game.map_id,
        "mode": obs.game.mode,
    }

def main():
    config = load_config(Path("runtime_config.json"))
    controller = MesenController(config["emulator"])

    # 1. Position prüfen
    print("Schritt 1: Position prüfen")
    state = get_state(controller)
    print(f"  Position: ({state['x']},{state['y']}), Richtung: {state['direction']}, Map: {state['map_id']}, Mode: {state['mode']}")

    # 2. Pre-Reset-Dump
    print("\nSchritt 2: Pre-Reset-Dump")
    pre_reset = dump_bridge(controller, "Pre-Reset")

    # 3. Sanduhr-Reset
    print("\nSchritt 3: Sanduhr-Reset (Select + Up + A)")
    controller.reset_room()
    time.sleep(2.0)

    # 4. Post-Reset-Dump
    print("\nSchritt 4: Post-Reset-Dump (Brücke sollte deaktiviert sein)")
    post_reset = dump_bridge(controller, "Post-Reset")

    # 5. Position nach Reset prüfen
    print("\nSchritt 5: Position nach Reset prüfen")
    state = get_state(controller)
    print(f"  Position: ({state['x']},{state['y']}), Richtung: {state['direction']}")

    # 6. Figur an Schussstelle bringen (28,24), Blickrichtung West
    target_x, target_y = 28, 24
    if state['x'] != target_x or state['y'] != target_y:
        print(f"\nSchritt 6: Figur an Schussstelle ({target_x},{target_y}) bringen")
        # Einfache Navigation: erst x, dann y
        while state['x'] != target_x:
            if state['x'] < target_x:
                controller.move("east", 1)
            else:
                controller.move("west", 1)
            time.sleep(0.5)
            state = get_state(controller)
            print(f"  -> ({state['x']},{state['y']})")
        while state['y'] != target_y:
            if state['y'] < target_y:
                controller.move("south", 1)
            else:
                controller.move("north", 1)
            time.sleep(0.5)
            state = get_state(controller)
            print(f"  -> ({state['x']},{state['y']})")

    # Blickrichtung West
    if state['direction'] != 'west':
        print(f"\nSchritt 7: Blickrichtung West (aktuell: {state['direction']})")
        controller.face("west")
        time.sleep(0.5)
        state = get_state(controller)
        print(f"  -> Richtung: {state['direction']}")

    # 8. Pfeil schießen
    print("\nSchritt 8: Pfeil schießen (use_tool)")
    controller.use_tool()
    time.sleep(1.5)

    # 9. Post-Arrow-Dump
    print("\nSchritt 9: Post-Arrow-Dump (Brücke sollte aktiviert sein)")
    post_arrow = dump_bridge(controller, "Post-Arrow")

    # 10. Diffs
    print("\n=== Diffs ===")
    for pos in pre_reset:
        pre = pre_reset[pos]["value"]
        post_r = post_reset[pos]["value"]
        post_a = post_arrow[pos]["value"]
        changed = "CHANGED" if post_r != post_a else "same"
        print(f"  {pos}: pre={pre} -> post_reset={post_r} -> post_arrow={post_a} [{changed}]")

    print("\nTest abgeschlossen.")

if __name__ == "__main__":
    main()
