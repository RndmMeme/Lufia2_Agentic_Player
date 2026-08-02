# Mesen WRAM utilities

The active runtime uses Mesen's Lua API to read coherent SNES Work RAM and send
frame-bounded controller input.

```powershell
python wram_discovery\mesen_bridge.py doctor
python wram_discovery\mesen_bridge.py read 0x05AC 2
python wram_discovery\mesen_bridge.py dump capture.bin
python wram_discovery\mesen_bridge.py screenshot frame.png
python wram_discovery\mesen_bridge.py press a --frames 1
```

Load [mesen_wram_bridge.lua](./mesen_bridge/mesen_wram_bridge.lua) in Mesen with
I/O access enabled. The file transport under `mesen_bridge/shared/` is volatile
and ignored by Git.

Authoritative decoded results live in:

- `data/lufia2_wram_base_of_truth.json`
- `docs/lufia2_wram_base_of_truth.md`
- `docs/lufia2_wram_checklist_merged_update_v5.txt`

The remaining extraction scripts rebuild monster action/movement tables from
the ROM reference. One-off audits, old dumps, campaigns, and the optional
Snes9x discovery backend are preserved under `legacy/wram_research/`.
