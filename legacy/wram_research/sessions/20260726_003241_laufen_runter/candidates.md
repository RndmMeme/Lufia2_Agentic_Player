# WRAM candidates: laufen runter

- Trials: 5
- WRAM: 131072 bytes
- Score: repeatable action changes, discounted by control-window noise

## Richtungsanalyse (Runter: Y steigt)

Diese Bytes folgen in mindestens 80 % der Wiederholungen der erwarteten Richtung und bleiben im Kontrollfenster ruhig:

| Address | Score | Richtung | Control | Checklist | Deltas |
|---|---:|---:|---:|---|---|
| 7E:236E | 258.00 | 5/5 | 5/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | +16 x4, +32 x1 |
| 7E:28AA | 258.00 | 5/5 | 5/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| Stadt-Y: 7E:28AA | +16 x4, +32 x1 |
| 7E:353A | 258.00 | 5/5 | 5/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | +16 x4, +32 x1 |
| 7E:353C | 258.00 | 5/5 | 5/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | +16 x4, +32 x1 |
| 7E:2CB5 | 160.00 | 5/5 | 5/5 | [x] 7E:2CB5–7E:2CB9 = Richtungsverlauf/FIFO | +1 x5 |
| 7E:2345 | 158.00 | 5/5 | 5/5 | unmentioned | +5 x4, +18 x1 |
| 7E:23B5 | 158.00 | 5/5 | 5/5 | unmentioned | +16 x4, +32 x1 |
| 7E:28AE | 158.00 | 5/5 | 5/5 | unmentioned | +16 x4, +32 x1 |
| 7E:28BA | 158.00 | 5/5 | 5/5 | unmentioned | +16 x4, +32 x1 |
| 7E:29F6 | 158.00 | 5/5 | 5/5 | unmentioned | +1 x4, +2 x1 |
| 7E:245E | 156.00 | 5/5 | 5/5 | unmentioned | +4 x3, +24 x2 |
| 7E:2462 | 156.00 | 5/5 | 5/5 | unmentioned | +4 x3, +24 x2 |
| 7E:645E | 140.00 | 4/5 | 5/5 | unmentioned | +1 x4 |
| 7F:061A | 140.00 | 4/5 | 5/5 | unmentioned | +1 x4 |
| 7F:F80A | 140.00 | 4/5 | 5/5 | unmentioned | +1 x4 |
| 7E:233C | 137.50 | 4/5 | 5/5 | unmentioned | +15 x3, +16 x1 |
| 7E:239D | 137.50 | 4/5 | 5/5 | unmentioned | +15 x3, +16 x1 |
| 7E:3543 | 137.50 | 4/5 | 5/5 | unmentioned | +7 x3, +47 x1 |
| 7E:3545 | 137.50 | 4/5 | 5/5 | unmentioned | +7 x3, +39 x1 |
| 7F:0618 | 137.50 | 4/5 | 5/5 | unmentioned | +1 x3, +3 x1 |

## Bereits in der Checkliste gepflegte Treffer

Diese bereits gepflegten Adressen änderten sich zeitgleich. Das bestätigt Korrelation, nicht automatisch die Ursache:

| Address | Score | Action | Control | Checklist | Transitions |
|---|---:|---:|---:|---|---|
| 7E:2CB5 | 100.00 | 5/5 | 0/5 | [x] 7E:2CB5–7E:2CB9 = Richtungsverlauf/FIFO | 00->01 x5 |
| 7E:236E | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 10->20 x4, 10->30 x1 |
| 7E:28AA | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| Stadt-Y: 7E:28AA | 00->10 x4, 00->20 x1 |
| 7E:353A | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | 00->10 x4, 00->20 x1 |
| 7E:353C | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | 00->10 x4, 00->20 x1 |
| 7E:2455 | 90.00 | 5/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot \| aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 6F->5F x3, 8F->6F x1, 7F->6F x1 |
| 7E:2CB9 | 35.00 | 2/5 | 0/5 | [x] 7E:2CB5–7E:2CB9 = Richtungsverlauf/FIFO | 00->01 x1, 01->00 x1 |
| 7E:4304 | 21.00 | 2/5 | 2/5 | [~] IP-Fähigkeit der ausgerüsteten Weapon \| Equipment-Metadaten: 7E:42DD–7E:4304 | A8->63 x1, A6->63 x1 |

## Alle Kandidaten

| Rank | Address | Score | Action | Control | Checklist | Transitions |
|---:|---|---:|---:|---:|---|---|
| 1 | 7E:297E | 100.00 | 5/5 | 0/5 | unmentioned | 04->00 x5 |
| 2 | 7E:29A6 | 100.00 | 5/5 | 0/5 | unmentioned | 04->00 x5 |
| 3 | 7E:2CB5 | 100.00 | 5/5 | 0/5 | [x] 7E:2CB5–7E:2CB9 = Richtungsverlauf/FIFO | 00->01 x5 |
| 4 | 7E:3785 | 100.00 | 5/5 | 0/5 | unmentioned | 04->00 x5 |
| 5 | 7E:6436 | 100.00 | 5/5 | 0/5 | unmentioned | 11->10 x5 |
| 6 | 7E:2345 | 95.00 | 5/5 | 0/5 | unmentioned | 11->16 x4, 04->16 x1 |
| 7 | 7E:236E | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 10->20 x4, 10->30 x1 |
| 8 | 7E:23A5 | 95.00 | 5/5 | 0/5 | unmentioned | 2F->1F x4, 2F->0F x1 |
| 9 | 7E:23B5 | 95.00 | 5/5 | 0/5 | unmentioned | 00->10 x4, 00->20 x1 |
| 10 | 7E:246D | 95.00 | 5/5 | 0/5 | unmentioned | 5F->4F x4, 5F->3F x1 |
| 11 | 7E:2471 | 95.00 | 5/5 | 0/5 | unmentioned | 6F->5F x4, 6F->4F x1 |
| 12 | 7E:2475 | 95.00 | 5/5 | 0/5 | unmentioned | 3F->2F x4, 3F->1F x1 |
| 13 | 7E:2479 | 95.00 | 5/5 | 0/5 | unmentioned | 4F->3F x4, 4F->2F x1 |
| 14 | 7E:247D | 95.00 | 5/5 | 0/5 | unmentioned | 3F->2F x4, 3F->1F x1 |
| 15 | 7E:2481 | 95.00 | 5/5 | 0/5 | unmentioned | 4F->3F x4, 4F->2F x1 |
| 16 | 7E:2485 | 95.00 | 5/5 | 0/5 | unmentioned | 2F->1F x4, 2F->0F x1 |
| 17 | 7E:2489 | 95.00 | 5/5 | 0/5 | unmentioned | 3F->2F x4, 3F->1F x1 |
| 18 | 7E:28AA | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| Stadt-Y: 7E:28AA | 00->10 x4, 00->20 x1 |
| 19 | 7E:28AE | 95.00 | 5/5 | 0/5 | unmentioned | 00->10 x4, 00->20 x1 |
| 20 | 7E:28BA | 95.00 | 5/5 | 0/5 | unmentioned | 00->10 x4, 00->20 x1 |
| 21 | 7E:29F6 | 95.00 | 5/5 | 0/5 | unmentioned | 07->08 x4, 07->09 x1 |
| 22 | 7E:34FF | 95.00 | 5/5 | 0/5 | unmentioned | 00->C0 x4, 80->00 x1 |
| 23 | 7E:353A | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | 00->10 x4, 00->20 x1 |
| 24 | 7E:353C | 95.00 | 5/5 | 0/5 | [~] Spieler-Y \| Dungeon-Y-Paar: 7E:353A / 7E:353C | 00->10 x4, 00->20 x1 |
| 25 | 7F:F80A | 95.00 | 5/5 | 0/5 | unmentioned | 00->01 x4, 55->01 x1 |
| 26 | 7E:2455 | 90.00 | 5/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot \| aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 6F->5F x3, 8F->6F x1, 7F->6F x1 |
| 27 | 7E:2459 | 90.00 | 5/5 | 0/5 | unmentioned | 7F->6F x3, 9F->7F x1, 8F->7F x1 |
| 28 | 7E:245D | 90.00 | 5/5 | 0/5 | unmentioned | 6F->5F x3, 7F->5F x1, 6F->4F x1 |
| 29 | 7E:2461 | 90.00 | 5/5 | 0/5 | unmentioned | 7F->6F x3, 8F->6F x1, 7F->5F x1 |
| 30 | 7E:2465 | 90.00 | 5/5 | 0/5 | unmentioned | 5F->4F x3, 6F->5F x2 |
| 31 | 7E:2469 | 90.00 | 5/5 | 0/5 | unmentioned | 6F->5F x3, 7F->6F x2 |
| 32 | 7E:34EF | 90.00 | 5/5 | 0/5 | unmentioned | FC->9C x3, 01->9C x1, 9D->FC x1 |
| 33 | 7E:3500 | 90.00 | 5/5 | 0/5 | unmentioned | 2A->28 x3, 00->28 x1, 28->2A x1 |
| 34 | 7E:245E | 85.00 | 5/5 | 0/5 | unmentioned | 88->8C x2, 8C->A4 x1, 88->A0 x1, A0->A4 x1 |
| 35 | 7E:2462 | 85.00 | 5/5 | 0/5 | unmentioned | 8A->8E x2, 8E->A6 x1, 8A->A2 x1, A2->A6 x1 |
| 36 | 7E:2466 | 85.00 | 5/5 | 0/5 | unmentioned | A4->A0 x2, A0->8C x1, A4->88 x1, 88->8C x1 |
| 37 | 7E:246A | 85.00 | 5/5 | 0/5 | unmentioned | A6->A2 x2, A2->8E x1, A6->8A x1, 8A->8E x1 |
| 38 | 7E:34FD | 85.00 | 5/5 | 0/5 | unmentioned | 80->40 x2, 40->80 x1, 00->40 x1, C0->80 x1 |
| 39 | 7E:3501 | 85.00 | 5/5 | 0/5 | unmentioned | 40->00 x2, 00->40 x1, 40->80 x1, 80->40 x1 |
| 40 | 7F:0616 | 85.00 | 5/5 | 0/5 | unmentioned | 03->02 x2, 02->00 x1, 03->01 x1, 01->00 x1 |
| 41 | 7F:0618 | 85.00 | 5/5 | 0/5 | unmentioned | 00->01 x2, 01->02 x1, 00->03 x1, 03->02 x1 |
| 42 | 7E:29F7 | 80.00 | 4/5 | 0/5 | unmentioned | 08->07 x4 |
| 43 | 7E:3542 | 80.00 | 4/5 | 0/5 | unmentioned | 00->80 x4 |
| 44 | 7E:3544 | 80.00 | 4/5 | 0/5 | unmentioned | 00->80 x4 |
| 45 | 7E:645E | 80.00 | 4/5 | 0/5 | unmentioned | 00->01 x4 |
| 46 | 7E:233C | 75.00 | 4/5 | 0/5 | unmentioned | 00->0F x3, 00->10 x1 |
| 47 | 7E:2344 | 75.00 | 4/5 | 0/5 | unmentioned | 92->42 x3, BE->42 x1 |
| 48 | 7E:239D | 75.00 | 4/5 | 0/5 | unmentioned | 00->0F x3, 00->10 x1 |
| 49 | 7E:2456 | 75.00 | 4/5 | 0/5 | unmentioned | A0->A4 x3, 8C->88 x1 |
| 50 | 7E:245A | 75.00 | 4/5 | 0/5 | unmentioned | A2->A6 x3, 8E->8A x1 |
| 51 | 7E:3543 | 75.00 | 4/5 | 0/5 | unmentioned | 28->2F x3, 00->2F x1 |
| 52 | 7E:3545 | 75.00 | 4/5 | 0/5 | unmentioned | 20->27 x3, 00->27 x1 |
| 53 | 7F:0614 | 75.00 | 4/5 | 0/5 | unmentioned | 01->00 x3, 02->03 x1 |
| 54 | 7E:2348 | 70.00 | 4/5 | 0/5 | unmentioned | EC->84 x2, 00->C4 x1, 9C->C4 x1 |
| 55 | 7E:246E | 70.00 | 4/5 | 0/5 | unmentioned | A4->A0 x2, 8C->88 x2 |
| 56 | 7E:2472 | 70.00 | 4/5 | 0/5 | unmentioned | A6->A2 x2, 8E->8A x2 |
| 57 | 7E:29F8 | 70.00 | 4/5 | 0/5 | unmentioned | 09->08 x2, 07->08 x2 |
| 58 | 7E:29F9 | 70.00 | 4/5 | 0/5 | unmentioned | 08->07 x2, 0A->09 x1, 08->09 x1 |
| 59 | 7E:34F3 | 70.00 | 4/5 | 0/5 | unmentioned | 9C->9D x2, 00->FC x1, 9D->FC x1 |
| 60 | 7F:061A | 70.00 | 4/5 | 0/5 | unmentioned | 00->01 x2, 02->03 x2 |
| 61 | 7E:2338 | 60.00 | 3/5 | 0/5 | unmentioned | 00->80 x3 |
| 62 | 7E:2339 | 60.00 | 3/5 | 0/5 | unmentioned | 00->07 x3 |
| 63 | 7E:2341 | 60.00 | 3/5 | 0/5 | unmentioned | 08->88 x3 |
| 64 | 7E:2342 | 60.00 | 3/5 | 0/5 | unmentioned | 00->07 x3 |
| 65 | 7E:2457 | 60.00 | 3/5 | 0/5 | unmentioned | 22->24 x3 |
| 66 | 7E:245B | 60.00 | 3/5 | 0/5 | unmentioned | 22->24 x3 |
| 67 | 7E:2467 | 60.00 | 3/5 | 0/5 | unmentioned | 24->22 x3 |
| 68 | 7E:246B | 60.00 | 3/5 | 0/5 | unmentioned | 24->22 x3 |
| 69 | 7E:2349 | 55.00 | 3/5 | 0/5 | unmentioned | C0->80 x2, 40->00 x1 |
| 70 | 7E:2980 | 55.00 | 3/5 | 0/5 | unmentioned | 04->00 x2, 00->04 x1 |
| 71 | 7E:29A8 | 55.00 | 3/5 | 0/5 | unmentioned | 04->00 x2, 00->04 x1 |
| 72 | 7E:29B1 | 55.00 | 3/5 | 0/5 | unmentioned | 00->04 x2, 04->06 x1 |
| 73 | 7E:2CB7 | 55.00 | 3/5 | 0/5 | unmentioned | 00->01 x2, 01->00 x1 |
| 74 | 7E:34F1 | 55.00 | 3/5 | 0/5 | unmentioned | 9D->FC x2, 01->9D x1 |
| 75 | 7E:34FE | 55.00 | 3/5 | 0/5 | unmentioned | 28->2A x2, 2A->28 x1 |
| 76 | 7E:3503 | 55.00 | 3/5 | 0/5 | unmentioned | C0->80 x2, 40->00 x1 |
| 77 | 7E:3787 | 55.00 | 3/5 | 0/5 | unmentioned | 04->00 x2, 00->04 x1 |
| 78 | 7E:675A | 55.00 | 3/5 | 0/5 | unmentioned | 01->00 x2, 00->01 x1 |
| 79 | 7E:298F | 52.00 | 4/5 | 1/5 | unmentioned | 00->04 x1, 06->04 x1, 02->06 x1, 01->00 x1 |
| 80 | 7E:29DA | 52.00 | 4/5 | 1/5 | unmentioned | 02->03 x1, 04->05 x1, 06->05 x1, 04->03 x1 |
| 81 | 7E:2355 | 50.00 | 3/5 | 0/5 | unmentioned | E0->E1 x1, E1->E2 x1, E2->E3 x1 |
| 82 | 7E:2357 | 50.00 | 3/5 | 0/5 | unmentioned | E0->E1 x1, E1->E2 x1, E2->E3 x1 |
| 83 | 7E:298A | 50.00 | 3/5 | 0/5 | unmentioned | 04->06 x1, 06->02 x1, 02->00 x1 |
| 84 | 7E:2994 | 50.00 | 3/5 | 0/5 | unmentioned | 00->02 x1, 02->06 x1, 06->04 x1 |
| 85 | 7E:29B2 | 50.00 | 3/5 | 0/5 | unmentioned | 04->06 x1, 06->02 x1, 02->00 x1 |
| 86 | 7E:29BC | 50.00 | 3/5 | 0/5 | unmentioned | 00->02 x1, 02->06 x1, 06->04 x1 |
| 87 | 7E:3502 | 50.00 | 3/5 | 0/5 | unmentioned | 00->2A x1, 2A->28 x1, 28->2A x1 |
| 88 | 7E:6A9D | 48.00 | 3/5 | 1/5 | unmentioned | 00->01 x3 |
| 89 | 7E:2989 | 44.00 | 3/5 | 1/5 | unmentioned | 00->04 x2, 04->06 x1 |
| 90 | 7E:29B6 | 44.00 | 3/5 | 1/5 | unmentioned | 00->04 x2, 02->06 x1 |
| 91 | 7E:662B | 44.00 | 3/5 | 1/5 | unmentioned | 01->00 x2, 00->01 x1 |
| 92 | 7E:6701 | 44.00 | 3/5 | 1/5 | unmentioned | 00->01 x2, 01->00 x1 |
| 93 | 7E:245F | 40.00 | 2/5 | 0/5 | unmentioned | 22->24 x2 |
| 94 | 7E:2463 | 40.00 | 2/5 | 0/5 | unmentioned | 22->24 x2 |
| 95 | 7E:246F | 40.00 | 2/5 | 0/5 | unmentioned | 24->22 x2 |
| 96 | 7E:2473 | 40.00 | 2/5 | 0/5 | unmentioned | 24->22 x2 |
| 97 | 7E:297F | 40.00 | 2/5 | 0/5 | unmentioned | 00->04 x2 |
| 98 | 7E:29A7 | 40.00 | 2/5 | 0/5 | unmentioned | 00->04 x2 |
| 99 | 7E:2A06 | 40.00 | 2/5 | 0/5 | unmentioned | 31->30 x2 |
| 100 | 7E:2CB6 | 40.00 | 2/5 | 0/5 | unmentioned | 01->00 x2 |
