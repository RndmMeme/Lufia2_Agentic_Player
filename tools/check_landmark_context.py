r"""Check if the completed landmark appears in the LLM context."""

from agent.orchestrator import MesenOrchestrator
from agent.config import load_config
from pathlib import Path

config = load_config(Path("runtime_config.json"))
orchestrator = MesenOrchestrator(config, "test", Path("data/runs/qwen_cave_probe_01"), execute=False)
obs = orchestrator.controller.observe()
orchestrator.mapper = orchestrator._load_mapper(obs.game.map_id)
orchestrator.mapper.observe(obs.navigation)

context = orchestrator._context(obs)
room = context.get("navigation", {}).get("current_room", {})
print("Current room:", room.get("id"))
for landmark in room.get("nearby_live_landmarks", []):
    print(f"  Landmark: {landmark.get('id')}")
    print(f"    completed: {landmark.get('completed')}")
    print(f"    action_readiness: {landmark.get('action_readiness')}")
