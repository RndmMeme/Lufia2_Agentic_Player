# Gameplay-WRAM-Audit

Die Helper-Offets sind Snes9x-Hostspiegel-Offets, keine echten SNES-WRAM-Offets.
Für den zusammenhängenden Helper-Gameplayblock gilt in diesem Live-Test:

`Mesen snesWorkRam offset = legacy helper offset - 0x2314`

Ergebnis: `{'CONTRADICTED': 2, 'CONFIRMED': 35, 'OBSERVED': 5, 'UNRELIABLE': 1}`

| Status | Angabe | Legacy | Mesen | Beobachtet | Beleg |
|---|---|---|---|---|---|
| CONTRADICTED | Helper offsets are true SNES-WRAM offsets | 0x02D8F | 7E:2D8F (0x02D8F) | 18 58 18 5A | 18 58 18 5A are impossible party IDs; visible party is Guy/Arty/Selan/Tia |
| CONFIRMED | Party order and IDs | 0x02D8F | 7E:0A7B (0x00A7B) | 02 03 01 04 = Guy, Arty, Selan, Tia | exact match with gameplay/menu_stable.png |
| CONFIRMED | Gold uint24 little-endian | 0x02D9E | 7E:0A8A (0x00A8A) | 2D 94 98 = 9999405 | menu_stable.png visibly shows GOLD 9999405 |
| CONFIRMED | Inventory stream start and ordering | 0x02DA1 | 7E:0A8D (0x00A8D) | first IDs 16 01 2C 29 0C 1E | item_menu.png shows Brave, Charred Newt, Curselifter, Escape, Shriek, Freeze Ball in this order |
| CONFIRMED | Guy: level, current/max HP and current/max MP | 0x0303A | 7E:0D26 (0x00D26) | Lv/HP/MaxHP/MP/MaxMP = (99, 828, 828, 471, 471) | exact match with menu_stable.png |
| CONFIRMED | Arty: level, current/max HP and current/max MP | 0x030F8 | 7E:0DE4 (0x00DE4) | Lv/HP/MaxHP/MP/MaxMP = (99, 568, 568, 0, 0) | exact match with menu_stable.png |
| CONFIRMED | Selan: level, current/max HP and current/max MP | 0x02F7C | 7E:0C68 (0x00C68) | Lv/HP/MaxHP/MP/MaxMP = (99, 642, 642, 547, 547) | exact match with menu_stable.png |
| CONFIRMED | Tia: level, current/max HP and current/max MP | 0x031B6 | 7E:0EA2 (0x00EA2) | Lv/HP/MaxHP/MP/MaxMP = (99, 619, 619, 372, 372) | exact match with menu_stable.png |
| CONFIRMED | Guy: ATP/DFP/STR/AGL/INT/GUT/MGR | 0x0303A | 7E:0D52 (0x00D52) | (571, 429, 183, 108, 284, 83, 246) | exact match with status_guy_stable.png |
| CONFIRMED | Guy: equipped weapon/armor/hands/head/ring/jewel | 0x0303A | 7E:0D8F (0x00D8F) | 0078 00DE 00F9 013A 0153 0187 | Zirco ax / Zircon plate / Mage shield / Old helmet / Sonic Ring / Black Eye; exact match with status_guy_stable.png |
| CONFIRMED | Guy: IP raw value | 0x030F9 | 7E:0DE5 (0x00DE5) | 60 (96) -> visible 37% | status_guy_stable.png confirms intentional next-block overlap |
| CONFIRMED | Arty: ATP/DFP/STR/AGL/INT/GUT/MGR | 0x030F8 | 7E:0E10 (0x00E10) | (765, 563, 377, 187, 209, 113, 278) | exact match with status_party_2.png |
| CONFIRMED | Arty: equipped weapon/armor/hands/head/ring/jewel | 0x030F8 | 7E:0E4D (0x00E4D) | 0078 00CE 0103 013A 015A 0187 | Zirco ax / Crystal mail / Zirco gloves / Old helmet / S-Thun ring / Black Eye; exact match with status_party_2.png |
| CONFIRMED | Arty: IP raw value | 0x031B7 | 7E:0EA3 (0x00EA3) | 09 (9) -> visible 3% | status_party_2.png confirms intentional next-block overlap |
| CONFIRMED | Selan: ATP/DFP/STR/AGL/INT/GUT/MGR | 0x02F7C | 7E:0C94 (0x00C94) | (752, 562, 389, 266, 143, 83, 187) | exact match with status_party_4.png |
| CONFIRMED | Selan: equipped weapon/armor/hands/head/ring/jewel | 0x02F7C | 7E:0CD1 (0x00CD1) | 0064 00D3 0104 0138 0150 0187 | Bustery sword / Deadly armor / Zirco shield / Zirco band / Thunder ring / Black Eye; exact match with status_party_4.png |
| CONFIRMED | Selan: IP raw value | 0x0303B | 7E:0D27 (0x00D27) | 20 (32) -> visible 12% | status_party_4.png confirms intentional next-block overlap |
| CONFIRMED | Tia: ATP/DFP/STR/AGL/INT/GUT/MGR | 0x031B6 | 7E:0ECE (0x00ECE) | (479, 336, 132, 140, 188, 81, 205) | exact match with status_party_3.png |
| CONFIRMED | Tia: equipped weapon/armor/hands/head/ring/jewel | 0x031B6 | 7E:0F0B (0x00F0B) | 0067 00CB 00EE 0138 015A 0181 | Lizard blow / Plati plate / Anger brace / Zirco band / S-Thun ring / Kraken rock; exact match with status_party_3.png |
| CONFIRMED | Tia: IP raw value | 0x03275 | 7E:0F61 (0x00F61) | 4A (74) -> visible 29% | status_party_3.png confirms intentional next-block overlap |
| CONFIRMED | Selan character-name anchor | 0x02F7E | 7E:0C6A (0x00C6A) | SSelan at 7E:0C6A | found inside the corrected character block |
| CONFIRMED | Guy character-name anchor | 0x0303C | 7E:0D28 (0x00D28) | GGuy at 7E:0D28 | found inside the corrected character block |
| CONFIRMED | Arty character-name anchor | 0x030FA | 7E:0DE6 (0x00DE6) | AArty at 7E:0DE6 | found inside the corrected character block |
| CONFIRMED | Tia character-name anchor | 0x031B8 | 7E:0EA4 (0x00EA4) | TTia at 7E:0EA4 | found inside the corrected character block |
| CONFIRMED | Dekar character-name anchor | 0x03276 | 7E:0F62 (0x00F62) | DDekar at 7E:0F62 | found inside the corrected character block |
| CONFIRMED | Lexis character-name anchor | 0x03334 | 7E:1020 (0x01020) | LLexis at 7E:1020 | found inside the corrected character block |
| CONFIRMED | Direction FIFO: 01 south, 03 east | 0x02CB5 | 7E:09A1 (0x009A1) | Down capture 01 01 01 01 01; later Right capture 03 03 03 01 01 | normal controller presses plus live reads |
| CONFIRMED | Town X | 0x028A8 | 7E:0594 (0x00594) | 28 -> 58 | move_before.bin vs move_right.bin after visible Right movement |
| CONFIRMED | Town Y | 0x028AA | 7E:0596 (0x00596) | 80 -> A6 | move_before.bin vs move_after.bin after visible Down movement |
| CONFIRMED | Dungeon X high | 0x03532 | 7E:121E (0x0121E) | 20 -> 50 | move_before.bin vs move_right.bin after visible Right movement |
| CONFIRMED | Dungeon Y high | 0x0353A | 7E:1226 (0x01226) | 80 -> A6 | move_before.bin vs move_after.bin after visible Down movement |
| CONFIRMED | Local X | 0x02368 | 7E:0054 (0x00054) | 40 -> 70 | move_before.bin vs move_right.bin after visible Right movement |
| CONFIRMED | Local Y | 0x0236E | 7E:005A (0x0005A) | 90 -> B6 | move_before.bin vs move_after.bin after visible Down movement |
| OBSERVED | Scenario bitfield | 0x02C32 | 7E:091E (0x0091E) | FE FF 7F | corrected helper-block location; semantic transition not exercised |
| CONFIRMED | Capsule status bytes | 0x034CF | 7E:11BB (0x011BB) | 01 01 01 03 01 01 01 | all seven present; capsule_menu.png opens Sully; randomized capsule identity is position-dependent |
| OBSERVED | Dungeon flag bytes | 0x02A96 | 7E:0782 (0x00782) | 55 55 55 55 A1 6A 55 55 59 50 | corrected helper-block location; semantic transition not exercised |
| OBSERVED | Transport mode | 0x02CF5 | 7E:09E1 (0x009E1) | 00 | corrected helper-block location; semantic transition not exercised |
| OBSERVED | Walk/world coordinates | 0x0377F | 7E:146B (0x0146B) | 00 00 00 00 00 | corrected helper-block location; semantic transition not exercised |
| OBSERVED | Ship coordinates | 0x0379C | 7E:1488 (0x01488) | 02 04 00 00 0E | corrected helper-block location; semantic transition not exercised |
| CONFIRMED | Current Map ID | 0x028C0 | 7E:05AC (0x005AC) | 00 Overworld -> 05 Secret Skills Cave | uint8 map/floor ID; parent zone is derived through zones.txt |
| CONFIRMED | Previous/origin Map ID | 0x028C2 | 7E:05AE (0x005AE) | 05 Overworld -> 00 Secret Skills Cave | uint8 origin map; values are the inverse side of the tested transition |
| CONTRADICTED | Legacy 0x351E is Current Map ID | 0x0351E | 7E:120A (0x0120A) | 15 13 initially, later 00 00 without a map transition | wrong historical helper field; do not use 7E:351E or translated 7E:120A |
| UNRELIABLE | Blocked-step flag | 0x03586 | 7E:1272 (0x01272) | 9D | value is outside documented FF/00-03 domain and did not validate |
