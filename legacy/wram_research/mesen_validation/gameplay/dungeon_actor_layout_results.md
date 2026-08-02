# Dungeon-Actor-Layout-Audit

Status: **CONFIRMED**

- 40 Slots (`00`–`27`), Sprite `FF` = leer.
- Sprite: `7E:05D2 + Slot`.
- Tile-X/Y: `7E:06BA/06E2 + Slot`.
- Movement-State: `7E:066A + Slot`; Bit 0 = bewegt sich.
- Stabile Richtung: `7E:0692 + Slot`: 00 Süd, 02 West, 04 Nord, 06 Ost.
- Movement-Modus: `7E:070A + Slot`.
- Blickrichtung: `7F:E466 + Slot`, Bits 0–1.
- Blockierte Richtung: `7E:1272`: FF frei, 00 Nord, 01 Süd, 02 West, 03 Ost.
- Der kontrollierte Wandtest bestätigt `1272`, nicht die alte `3586`-Zuordnung.
