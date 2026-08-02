# Monster-ID-Tabelle

Quelle:
https://github.com/abyssonym/terrorwave/blob/master/tables/monster_overworld_sprites.txt

Lokale Datei: `monster_overworld_sprites.txt`

Spalten:

1. Battle-Monster-ID (hex)
2. Overworld-Sprite-ID (hex)
3. Monstername

Live gegen Mesen-WRAM verifiziert:

- `54 D8 Garbost` entspricht Enemy-Struct `+0x53 = 54`.
- `3B AE Ramia` entspricht Enemy-Struct `+0x53 = 3B`.
