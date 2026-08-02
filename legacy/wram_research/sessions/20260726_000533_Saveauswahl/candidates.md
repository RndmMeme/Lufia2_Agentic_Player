# WRAM candidates: Saveauswahl

- Trials: 5
- WRAM: 131072 bytes
- Score: repeatable action changes, discounted by control-window noise

## Bereits in der Checkliste gepflegte Treffer

Diese bereits gepflegten Adressen änderten sich zeitgleich. Das bestätigt Korrelation, nicht automatisch die Ursache:

| Address | Score | Action | Control | Checklist | Transitions |
|---|---:|---:|---:|---|---|
| 7E:2454 | 85.00 | 5/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot | 88->10 x2, 10->88 x2, 88->00 x1 |
| 7E:2435 | 20.00 | 1/5 | 0/5 | [x] aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 4E->F0 x1 |
| 7E:2455 | 20.00 | 1/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot \| aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 8C->F0 x1 |
| 7E:3534 | 90.00 | 5/5 | 0/5 | [~] Spieler-X \| Dungeon-X-Paar: 7E:3532 / 7E:3534 | 02->09 x3, 09->02 x2 |
| 7E:3888 | 90.00 | 5/5 | 0/5 | [x] Shop-Cursorposition | 03->02 x3, 02->03 x2 |
| 7E:379C | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 7E:379D | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 7E:37A0 | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-Y \| Ship-Y = (7E:37A0 << 8) \| 7E:379F. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 7E:2368 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Spieler hat seit letzter Aktion Position verändert \| 7E:2368 / 7E:236B = Dungeon-X lokal + Chunk/Page | 22->0E x1 |
| 7E:236E | 20.00 | 1/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 44->1E x1 |

## Alle Kandidaten

| Rank | Address | Score | Action | Control | Checklist | Transitions |
|---:|---|---:|---:|---:|---|---|
| 1 | 7E:3534 | 90.00 | 5/5 | 0/5 | [~] Spieler-X \| Dungeon-X-Paar: 7E:3532 / 7E:3534 | 02->09 x3, 09->02 x2 |
| 2 | 7E:3538 | 90.00 | 5/5 | 0/5 | unmentioned | 09->02 x3, 02->09 x2 |
| 3 | 7E:35F4 | 90.00 | 5/5 | 0/5 | unmentioned | 5F->7F x3, 7F->5F x2 |
| 4 | 7E:35F8 | 90.00 | 5/5 | 0/5 | unmentioned | 7F->5F x3, 5F->7F x2 |
| 5 | 7E:36A3 | 90.00 | 5/5 | 0/5 | unmentioned | 90->18 x3, 18->90 x2 |
| 6 | 7E:37C7 | 90.00 | 5/5 | 0/5 | unmentioned | 03->02 x3, 02->03 x2 |
| 7 | 7E:37EF | 90.00 | 5/5 | 0/5 | unmentioned | 01->00 x3, 00->01 x2 |
| 8 | 7E:3888 | 90.00 | 5/5 | 0/5 | [x] Shop-Cursorposition | 03->02 x3, 02->03 x2 |
| 9 | 7E:2454 | 85.00 | 5/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot | 88->10 x2, 10->88 x2, 88->00 x1 |
| 10 | 7E:2446 | 70.00 | 4/5 | 0/5 | unmentioned | 44->40 x2, 40->00 x1, 40->44 x1 |
| 11 | 7E:244A | 70.00 | 4/5 | 0/5 | unmentioned | 46->42 x2, 42->00 x1, 42->46 x1 |
| 12 | 7E:244E | 70.00 | 4/5 | 0/5 | unmentioned | 40->44 x2, 44->00 x1, 44->40 x1 |
| 13 | 7E:2452 | 70.00 | 4/5 | 0/5 | unmentioned | 42->46 x2, 46->00 x1, 46->42 x1 |
| 14 | 7E:3658 | 70.00 | 4/5 | 0/5 | unmentioned | D0->DB x2, DB->D0 x2 |
| 15 | 7E:3778 | 70.00 | 4/5 | 0/5 | unmentioned | 00->01 x2, 01->00 x2 |
| 16 | 7E:2355 | 65.00 | 4/5 | 0/5 | unmentioned | 65->66 x1, 66->67 x1, 69->6A x1, 6A->6B x1 |
| 17 | 7E:2357 | 65.00 | 4/5 | 0/5 | unmentioned | 65->66 x1, 66->67 x1, 69->6A x1, 6A->6B x1 |
| 18 | 7E:2871 | 65.00 | 4/5 | 0/5 | unmentioned | 9A->99 x1, 99->98 x1, 96->95 x1, 95->94 x1 |
| 19 | 7E:3654 | 55.00 | 3/5 | 0/5 | unmentioned | DB->D0 x2, D0->DB x1 |
| 20 | 7E:3774 | 55.00 | 3/5 | 0/5 | unmentioned | 01->00 x2, 00->01 x1 |
| 21 | 7E:286E | 26.00 | 4/5 | 3/5 | unmentioned | 03->01 x1, 02->03 x1, 04->0E x1, 04->01 x1 |
| 22 | 7E:2368 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Spieler hat seit letzter Aktion Position verändert \| 7E:2368 / 7E:236B = Dungeon-X lokal + Chunk/Page | 22->0E x1 |
| 23 | 7E:236C | 20.00 | 1/5 | 0/5 | unmentioned | 08->00 x1 |
| 24 | 7E:236E | 20.00 | 1/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 44->1E x1 |
| 25 | 7E:2372 | 20.00 | 1/5 | 0/5 | unmentioned | DC->DF x1 |
| 26 | 7E:2377 | 20.00 | 1/5 | 0/5 | unmentioned | 00->AA x1 |
| 27 | 7E:2378 | 20.00 | 1/5 | 0/5 | unmentioned | 00->0A x1 |
| 28 | 7E:2386 | 20.00 | 1/5 | 0/5 | unmentioned | 80->00 x1 |
| 29 | 7E:2432 | 20.00 | 1/5 | 0/5 | unmentioned | 62->00 x1 |
| 30 | 7E:2433 | 20.00 | 1/5 | 0/5 | unmentioned | 39->00 x1 |
| 31 | 7E:2434 | 20.00 | 1/5 | 0/5 | unmentioned | C0->00 x1 |
| 32 | 7E:2435 | 20.00 | 1/5 | 0/5 | [x] aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 4E->F0 x1 |
| 33 | 7E:2436 | 20.00 | 1/5 | 0/5 | unmentioned | 20->00 x1 |
| 34 | 7E:2437 | 20.00 | 1/5 | 0/5 | unmentioned | 39->00 x1 |
| 35 | 7E:2438 | 20.00 | 1/5 | 0/5 | unmentioned | C0->00 x1 |
| 36 | 7E:2439 | 20.00 | 1/5 | 0/5 | unmentioned | 5E->F0 x1 |
| 37 | 7E:243A | 20.00 | 1/5 | 0/5 | unmentioned | 22->00 x1 |
| 38 | 7E:243B | 20.00 | 1/5 | 0/5 | unmentioned | 39->00 x1 |
| 39 | 7E:243C | 20.00 | 1/5 | 0/5 | unmentioned | D8->00 x1 |
| 40 | 7E:243D | 20.00 | 1/5 | 0/5 | unmentioned | 4E->F0 x1 |
| 41 | 7E:243E | 20.00 | 1/5 | 0/5 | unmentioned | 80->00 x1 |
| 42 | 7E:243F | 20.00 | 1/5 | 0/5 | unmentioned | 39->00 x1 |
| 43 | 7E:2440 | 20.00 | 1/5 | 0/5 | unmentioned | D8->00 x1 |
| 44 | 7E:2441 | 20.00 | 1/5 | 0/5 | unmentioned | 5E->F0 x1 |
| 45 | 7E:2442 | 20.00 | 1/5 | 0/5 | unmentioned | 82->00 x1 |
| 46 | 7E:2443 | 20.00 | 1/5 | 0/5 | unmentioned | 39->00 x1 |
| 47 | 7E:2444 | 20.00 | 1/5 | 0/5 | unmentioned | 18->00 x1 |
| 48 | 7E:2445 | 20.00 | 1/5 | 0/5 | unmentioned | A6->F0 x1 |
| 49 | 7E:2447 | 20.00 | 1/5 | 0/5 | unmentioned | 3B->00 x1 |
| 50 | 7E:2448 | 20.00 | 1/5 | 0/5 | unmentioned | 18->00 x1 |
| 51 | 7E:2449 | 20.00 | 1/5 | 0/5 | unmentioned | B6->F0 x1 |
| 52 | 7E:244B | 20.00 | 1/5 | 0/5 | unmentioned | 3B->00 x1 |
| 53 | 7E:244C | 20.00 | 1/5 | 0/5 | unmentioned | 90->00 x1 |
| 54 | 7E:244D | 20.00 | 1/5 | 0/5 | unmentioned | A6->F0 x1 |
| 55 | 7E:244F | 20.00 | 1/5 | 0/5 | unmentioned | 3B->00 x1 |
| 56 | 7E:2450 | 20.00 | 1/5 | 0/5 | unmentioned | 90->00 x1 |
| 57 | 7E:2451 | 20.00 | 1/5 | 0/5 | unmentioned | B6->F0 x1 |
| 58 | 7E:2453 | 20.00 | 1/5 | 0/5 | unmentioned | 3B->00 x1 |
| 59 | 7E:2455 | 20.00 | 1/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot \| aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 8C->F0 x1 |
| 60 | 7E:2457 | 20.00 | 1/5 | 0/5 | unmentioned | 32->00 x1 |
| 61 | 7E:2615 | 20.00 | 1/5 | 0/5 | unmentioned | AA->2A x1 |
| 62 | 7E:2616 | 20.00 | 1/5 | 0/5 | unmentioned | AA->00 x1 |
| 63 | 7E:2617 | 20.00 | 1/5 | 0/5 | unmentioned | AA->00 x1 |
| 64 | 7E:2618 | 20.00 | 1/5 | 0/5 | unmentioned | 02->00 x1 |
| 65 | 7E:42F8 | 20.00 | 1/5 | 0/5 | unmentioned | 06->0A x1 |
| 66 | 7E:42FA | 20.00 | 1/5 | 0/5 | unmentioned | 17->06 x1 |
| 67 | 7E:42FB | 20.00 | 1/5 | 0/5 | unmentioned | A5->8C x1 |
| 68 | 7E:42FC | 20.00 | 1/5 | 0/5 | unmentioned | 80->67 x1 |
| 69 | 7E:42FD | 20.00 | 1/5 | 0/5 | unmentioned | 6E->8B x1 |
| 70 | 7E:42FE | 20.00 | 1/5 | 0/5 | unmentioned | 8B->86 x1 |
| 71 | 7E:2374 | 20.00 | 3/5 | 3/5 | unmentioned | D0->C0 x1, AB->C0 x1, D0->FC x1 |
| 72 | 7E:2375 | 16.00 | 1/5 | 1/5 | unmentioned | DF->DC x1 |
| 73 | 7E:2371 | 10.00 | 3/5 | 4/5 | unmentioned | B9->C0 x1, AB->E6 x1, B2->B9 x1 |
| 74 | 7E:2456 | 10.00 | 3/5 | 4/5 | unmentioned | 28->2A x1, 24->00 x1, 26->28 x1 |
| 75 | 7E:3643 | 10.00 | 3/5 | 4/5 | unmentioned | B9->C0 x1, AB->C0 x1, B2->B9 x1 |
| 76 | 7E:3763 | 10.00 | 3/5 | 4/5 | unmentioned | 04->05 x1, 02->05 x1, 03->04 x1 |
| 77 | 7E:2354 | 0.00 | 5/5 | 5/5 | unmentioned | 32->0C x1, F9->AC x1, 86->FF x1, 83->1B x1 |
| 78 | 7E:2356 | 0.00 | 5/5 | 5/5 | unmentioned | 32->0C x1, F9->AC x1, 86->FF x1, 83->1B x1 |
| 79 | 7E:2870 | 0.00 | 5/5 | 5/5 | unmentioned | CE->F4 x1, 07->54 x1, 7A->01 x1, 7D->E5 x1 |
| 80 | 7E:3793 | 0.00 | 5/5 | 5/5 | unmentioned | 01->05 x1, 02->03 x1, 01->06 x1, 06->04 x1 |
| 81 | 7E:379C | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 82 | 7E:379D | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 83 | 7E:37A0 | 0.00 | 5/5 | 5/5 | [x] Excerion-/Ship-Y \| Ship-Y = (7E:37A0 << 8) \| 7E:379F. | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 84 | 7E:37A1 | 0.00 | 5/5 | 5/5 | unmentioned | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 85 | 7E:37A2 | 0.00 | 5/5 | 5/5 | unmentioned | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 86 | 7E:37A3 | 0.00 | 5/5 | 5/5 | unmentioned | 07->0D x1, 10->0D x1, 03->0A x1, 06->0E x1 |
| 87 | 7E:42F3 | 0.00 | 5/5 | 5/5 | unmentioned | 31->0B x1, F8->AB x1, 85->FE x1, 82->1A x1 |
| 88 | 7E:235B | 0.00 | 4/5 | 5/5 | unmentioned | 00->20 x4 |
| 89 | 7E:235F | 0.00 | 4/5 | 5/5 | unmentioned | FF->DF x4 |
| 90 | 7E:2873 | 0.00 | 4/5 | 5/5 | unmentioned | 00->20 x4 |
| 91 | 7E:37A4 | 0.00 | 4/5 | 5/5 | unmentioned | 0B->01 x1, 0A->04 x1, 10->0A x1, 08->0A x1 |
| 92 | 7E:37A8 | 0.00 | 4/5 | 5/5 | unmentioned | 0B->01 x1, 0A->04 x1, 10->0A x1, 08->0A x1 |
