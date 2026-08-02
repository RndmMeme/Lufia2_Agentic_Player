import time
import os
import sys
import binascii
import logging

# Add the project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from emulator.memory_reader import MemoryReader

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_dump(reader):
    reader.send_command("DUMP_FILE")
    print("Waiting for binary dump to be written to disk...")
    for _ in range(60): # Timeout after 30 seconds
        path = reader.get_latest_dump_path()
        if path:
            try:
                with open(path, 'rb') as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading dump file: {e}")
                return None
        time.sleep(0.5)
    return None

def main():
    print("====================================================")
    print("   LUFIA 2 - AUTOMATED BATTLE FLAG FINDER (v1.0)   ")
    print("====================================================")
    print("This tool will help identify the 'In Battle' RAM flag.")
    
    reader = MemoryReader()
    print("\nAwaiting connection from C# Helper (please start it if not running)...")
    
    # Wait for connection
    while not reader.active_conn:
        time.sleep(1)
    print("Connected to C# Helper!")

    # Capture Baseline (Overworld)
    print("\n[STEP 1] STAND STILL on the World Map (or in a Dungeon).")
    input(">> Press Enter when ready to capture BASELINE state...")
    baseline = get_dump(reader)
    if not baseline:
        print("Error: Failed to receive baseline dump.")
        return

    # Capture Target (Battle)
    print("\n[STEP 2] Enter a BATTLE.")
    input(">> Press Enter once you are inside the Battle Menu...")
    battle = get_dump(reader)
    if not battle:
        print("Error: Failed to receive battle dump.")
        return

    # Capture Recovery (Back to Map)
    print("\n[STEP 3] Finish the battle and return to the Map.")
    input(">> Press Enter once you are back in control on the Map...")
    recovery = get_dump(reader)
    if not recovery:
        print("Error: Failed to receive recovery dump.")
        return

    # Analyze
    print("\n[ANALYSIS] Identifying Battle Flag candidates...")
    candidates = []
    
    # We look for bytes that:
    # 1. Changed between Baseline and Battle
    # 2. Returned to Baseline value in Recovery
    # 3. Specifically, we are often looking for 0x00 -> 0x01 (or similar)
    
    for i in range(len(baseline)):
        if baseline[i] != battle[i] and battle[i] != recovery[i] and baseline[i] == recovery[i]:
            # This is a strong candidate
            candidates.append({
                "addr": hex(i),
                "map_val": baseline[i],
                "battle_val": battle[i]
            })

    if not candidates:
        print("\nNo perfect candidates found. Listing all bytes that changed during battle:")
        for i in range(len(baseline)):
            if baseline[i] != battle[i]:
                print(f" - Offset {hex(i)}: {baseline[i]:02X} -> {battle[i]:02X}")
    else:
        print(f"\nFound {len(candidates)} candidates that toggled during battle and reverted after:")
        for c in candidates[:50]: # Show top 50
            print(f" - Address 0x7E{c['addr'][2:].upper().zfill(4)}: Map({c['map_val']:02X}) -> Battle({c['battle_val']:02X})")
            
    print("\nTIP: Look for addresses near 0x3500 (Map Data) or 0x0000-0x1000.")
    print("Once you've tested a candidate, add it to 'ram_map.json'.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting.")
