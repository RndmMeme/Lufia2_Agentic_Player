# WRAM candidates: Reden mit Priester

- Trials: 5
- WRAM: 131072 bytes
- Score: repeatable action changes, discounted by control-window noise
- Hinweis: 21878 geänderte Adressen deuten auf einen großen Bildschirm-/Textzustandswechsel. Für den eigentlichen Zustandswert ist eine Lifecycle-Aufnahme geeigneter.

## Bereits in der Checkliste gepflegte Treffer

Diese bereits gepflegten Adressen änderten sich zeitgleich. Das bestätigt Korrelation, nicht automatisch die Ursache:

| Address | Score | Action | Control | Checklist | Transitions |
|---|---:|---:|---:|---|---|
| 7E:2425 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | F0->10 x1 |
| 7E:5802 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->53 x1 |
| 7E:5809 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->20 x1 |
| 7E:5882 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->43 x1 |
| 7E:5889 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->20 x1 |
| 7E:5902 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->4C x1 |
| 7E:5909 | 20.00 | 1/5 | 0/5 | [x] Save-Dialog aktiv (Bei Priester) | 00->20 x1 |
| 7E:53E5 | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->21 x4, 00->3C x1 |
| 7E:53E6 | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->02 x4, 00->20 x1 |
| 7E:53EB | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->21 x4, 00->2C x1 |
| 7E:53EC | 95.00 | 5/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->08 x4, 00->56 x1 |
| 7E:53FC | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->18 x4, 00->41 x1 |
| 7E:5402 | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->1E x4, 00->79 x1 |
| 7E:5403 | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->21 x4, 00->3C x1 |
| 7E:5467 | 95.00 | 5/5 | 0/5 | [x] Save-Slot bennenen | 00->21 x4, 00->3C x1 |
| 7E:547F | 95.00 | 5/5 | 0/5 | [x] Save-Slot bennenen | 00->21 x4, 00->2D x1 |
| 7E:356F | 80.00 | 4/5 | 0/5 | [~] Dungeon-Spawn-X \| Dungeon-Spawn: X 7E:356F / Y 7E:3571 | 00->11 x4 |
| 7E:53F4 | 80.00 | 4/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->10 x4 |
| 7E:53F5 | 80.00 | 4/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->21 x4 |
| 7E:53F6 | 80.00 | 4/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->12 x4 |
| 7E:53FB | 80.00 | 4/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->21 x4 |
| 7E:5476 | 80.00 | 4/5 | 0/5 | [x] Save-Slot bennenen | 00->52 x4 |
| 7E:54E2 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D6 x4 |
| 7E:54E3 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->A0 x4 |
| 7E:54E5 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->A0 x4 |
| 7E:54E6 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D9 x4 |
| 7E:54EE | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D9 x4 |
| 7E:54FA | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D9 x4 |
| 7E:5500 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D8 x4 |
| 7E:5501 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->A0 x4 |
| 7E:5503 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->A0 x4 |
| 7E:5504 | 80.00 | 4/5 | 0/5 | [x] Save-Slot-Charaktername | 00->D8 x4 |
| 7E:4304 | 28.00 | 2/5 | 1/5 | [~] IP-Fähigkeit der ausgerüsteten Weapon \| Equipment-Metadaten: 7E:42DD–7E:4304 | BE->63 x1, 63->6A x1 |
| 7E:2368 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Spieler hat seit letzter Aktion Position verändert \| 7E:2368 / 7E:236B = Dungeon-X lokal + Chunk/Page | 40->22 x1 |
| 7E:236B | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Spieler hat seit letzter Aktion Position verändert \| 7E:2368 / 7E:236B = Dungeon-X lokal + Chunk/Page | 01->00 x1 |
| 7E:236E | 20.00 | 1/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 10->44 x1 |
| 7E:236F | 20.00 | 1/5 | 0/5 | [~] Spieler-Y \| Spieler hat seit letzter Aktion Position verändert \| 7E:236E / 7E:236F = Dungeon-Y lokal + Chunk/Page | 01->00 x1 |
| 7E:2414 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | 00->08 x1 |
| 7E:2415 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | F0->10 x1 |
| 7E:2435 | 20.00 | 1/5 | 0/5 | [x] aktueller geladener Save-Slot \| Überschreiben-Bestätigung | F0->38 x1 |
| 7E:2454 | 20.00 | 1/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot | 78->A8 x1 |
| 7E:2455 | 20.00 | 1/5 | 0/5 | [x] vier Save-Slot-Strukturen \| aktuell markierter Save-Slot \| aktueller geladener Save-Slot \| Überschreiben-Bestätigung | 8F->90 x1 |
| 7E:28A8 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Spieler hat seit letzter Aktion Position verändert \| Stadt-X: 7E:28A8 | 28->00 x1 |
| 7E:3532 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Dungeon-X-Paar: 7E:3532 / 7E:3534 | 20->00 x1 |
| 7E:3534 | 20.00 | 1/5 | 0/5 | [~] Spieler-X \| Dungeon-X-Paar: 7E:3532 / 7E:3534 | 20->00 x1 |
| 7E:379C | 20.00 | 1/5 | 0/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 02->00 x1 |
| 7E:379D | 20.00 | 1/5 | 0/5 | [x] Excerion-/Ship-X \| Ship-X = (7E:379D << 8) \| 7E:379C. | 02->00 x1 |
| 7E:3888 | 20.00 | 1/5 | 0/5 | [x] Shop-Cursorposition | FF->00 x1 |
| 7E:53DE | 20.00 | 1/5 | 0/5 | [~] IP-Fähigkeit der ausgerüsteten Weapon \| Equipment-Render-Pane: 7E:53DE–7E:56CE | 00->47 x1 |
| 7E:53E4 | 20.00 | 1/5 | 0/5 | [x] Normal Mode verfügbar | 00->20 x1 |
| 7E:5460 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | 00->14 x1 |
| 7E:5560 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | 00->12 x1 |
| 7E:5565 | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->3C x1 |
| 7E:5566 | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->34 x1 |
| 7E:556E | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->34 x1 |
| 7E:5583 | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->3C x1 |
| 7E:5584 | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->31 x1 |
| 7E:5587 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | 00->3C x1 |
| 7E:558C | 20.00 | 1/5 | 0/5 | [x] Save-Slot-Spielzeit | 00->31 x1 |
| 7E:5804 | 20.00 | 1/5 | 0/5 | [x] aktueller geladener Save-Slot | 00->41 x1 |
| 7E:5806 | 20.00 | 1/5 | 0/5 | [x] Save-Slot bennenen | 00->56 x1 |
| 7E:631A | 20.00 | 1/5 | 0/5 | [~] IP-Fähigkeit der ausgerüsteten Weapon \| Equipment-Name: 7E:631A | 00->7E x1 |
| 7E:642B | 20.00 | 1/5 | 0/5 | [~] Raumobjekt-/Live-Map-Buffer \| 7E:642B–7E:6FA6 = beobachteter Live-Map-Buffer in Secret Skills Cave | 00->3C x1 |

## Alle Kandidaten

| Rank | Address | Score | Action | Control | Checklist | Transitions |
|---:|---|---:|---:|---:|---|---|
| 1 | 7E:5404 | 100.00 | 5/5 | 0/5 | unmentioned | 00->20 x5 |
| 2 | 7E:2375 | 95.00 | 5/5 | 0/5 | unmentioned | 31->00 x4, 31->DC x1 |
| 3 | 7E:2379 | 95.00 | 5/5 | 0/5 | unmentioned | 1E->DA x4, 1E->00 x1 |
| 4 | 7E:237A | 95.00 | 5/5 | 0/5 | unmentioned | 23->20 x4, 23->00 x1 |
| 5 | 7E:2CAF | 95.00 | 5/5 | 0/5 | unmentioned | 00->82 x4, 00->80 x1 |
| 6 | 7E:53E2 | 95.00 | 5/5 | 0/5 | unmentioned | 00->DA x4, 00->79 x1 |
| 7 | 7E:53E3 | 95.00 | 5/5 | 0/5 | unmentioned | 00->20 x4, 00->3C x1 |
| 8 | 7E:53E5 | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->21 x4, 00->3C x1 |
| 9 | 7E:53E6 | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->02 x4, 00->20 x1 |
| 10 | 7E:53E7 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 11 | 7E:53EA | 95.00 | 5/5 | 0/5 | unmentioned | 00->06 x4, 00->4C x1 |
| 12 | 7E:53EB | 95.00 | 5/5 | 0/5 | [x] Normal Mode verfügbar | 00->21 x4, 00->2C x1 |
| 13 | 7E:53EC | 95.00 | 5/5 | 0/5 | [x] Retry Mode freigeschaltet | 00->08 x4, 00->56 x1 |
| 14 | 7E:53ED | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->2C x1 |
| 15 | 7E:53EE | 95.00 | 5/5 | 0/5 | unmentioned | 00->0A x4, 00->39 x1 |
| 16 | 7E:53EF | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 17 | 7E:53F0 | 95.00 | 5/5 | 0/5 | unmentioned | 00->0C x4, 00->39 x1 |
| 18 | 7E:53F1 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 19 | 7E:53FC | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->18 x4, 00->41 x1 |
| 20 | 7E:53FD | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 21 | 7E:53FE | 95.00 | 5/5 | 0/5 | unmentioned | 00->1A x4, 00->72 x1 |
| 22 | 7E:53FF | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 23 | 7E:5400 | 95.00 | 5/5 | 0/5 | unmentioned | 00->1C x4, 00->74 x1 |
| 24 | 7E:5401 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 25 | 7E:5402 | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->1E x4, 00->79 x1 |
| 26 | 7E:5403 | 95.00 | 5/5 | 0/5 | [x] Gift Mode freigeschaltet | 00->21 x4, 00->3C x1 |
| 27 | 7E:5405 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 28 | 7E:5424 | 95.00 | 5/5 | 0/5 | unmentioned | 00->01 x4, 00->38 x1 |
| 29 | 7E:5425 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 30 | 7E:5426 | 95.00 | 5/5 | 0/5 | unmentioned | 00->03 x4, 00->32 x1 |
| 31 | 7E:5427 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 32 | 7E:5428 | 95.00 | 5/5 | 0/5 | unmentioned | 00->05 x4, 00->38 x1 |
| 33 | 7E:5429 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 34 | 7E:542A | 95.00 | 5/5 | 0/5 | unmentioned | 00->07 x4, 00->2F x1 |
| 35 | 7E:542B | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 36 | 7E:542C | 95.00 | 5/5 | 0/5 | unmentioned | 00->09 x4, 00->38 x1 |
| 37 | 7E:542D | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 38 | 7E:542E | 95.00 | 5/5 | 0/5 | unmentioned | 00->0B x4, 00->32 x1 |
| 39 | 7E:542F | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 40 | 7E:5430 | 95.00 | 5/5 | 0/5 | unmentioned | 00->0D x4, 00->38 x1 |
| 41 | 7E:5431 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 42 | 7E:543C | 95.00 | 5/5 | 0/5 | unmentioned | 00->19 x4, 00->11 x1 |
| 43 | 7E:543D | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->2D x1 |
| 44 | 7E:543E | 95.00 | 5/5 | 0/5 | unmentioned | 00->1B x4, 00->12 x1 |
| 45 | 7E:543F | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->2D x1 |
| 46 | 7E:5442 | 95.00 | 5/5 | 0/5 | unmentioned | 00->1F x4, 00->35 x1 |
| 47 | 7E:5443 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 48 | 7E:5444 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->36 x1 |
| 49 | 7E:5445 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 50 | 7E:5446 | 95.00 | 5/5 | 0/5 | unmentioned | 00->DB x4, 00->38 x1 |
| 51 | 7E:5447 | 95.00 | 5/5 | 0/5 | unmentioned | 00->60 x4, 00->3C x1 |
| 52 | 7E:5464 | 95.00 | 5/5 | 0/5 | unmentioned | 00->40 x4, 00->34 x1 |
| 53 | 7E:5465 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 54 | 7E:5466 | 95.00 | 5/5 | 0/5 | unmentioned | 00->42 x4, 00->37 x1 |
| 55 | 7E:5467 | 95.00 | 5/5 | 0/5 | [x] Save-Slot bennenen | 00->21 x4, 00->3C x1 |
| 56 | 7E:5468 | 95.00 | 5/5 | 0/5 | unmentioned | 00->44 x4, 00->31 x1 |
| 57 | 7E:5469 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 58 | 7E:546A | 95.00 | 5/5 | 0/5 | unmentioned | 00->46 x4, 00->2F x1 |
| 59 | 7E:546B | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 60 | 7E:546C | 95.00 | 5/5 | 0/5 | unmentioned | 00->48 x4, 00->34 x1 |
| 61 | 7E:546D | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 62 | 7E:546E | 95.00 | 5/5 | 0/5 | unmentioned | 00->4A x4, 00->37 x1 |
| 63 | 7E:546F | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 64 | 7E:5470 | 95.00 | 5/5 | 0/5 | unmentioned | 00->4C x4, 00->31 x1 |
| 65 | 7E:5471 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 66 | 7E:547C | 95.00 | 5/5 | 0/5 | unmentioned | 00->58 x4, 00->13 x1 |
| 67 | 7E:547D | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->2D x1 |
| 68 | 7E:547E | 95.00 | 5/5 | 0/5 | unmentioned | 00->5A x4, 00->14 x1 |
| 69 | 7E:547F | 95.00 | 5/5 | 0/5 | [x] Save-Slot bennenen | 00->21 x4, 00->2D x1 |
| 70 | 7E:5482 | 95.00 | 5/5 | 0/5 | unmentioned | 00->5E x4, 00->20 x1 |
| 71 | 7E:5483 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 72 | 7E:5484 | 95.00 | 5/5 | 0/5 | unmentioned | 00->60 x4, 00->20 x1 |
| 73 | 7E:5485 | 95.00 | 5/5 | 0/5 | unmentioned | 00->21 x4, 00->3C x1 |
| 74 | 7E:5486 | 95.00 | 5/5 | 0/5 | unmentioned | 00->DA x4, 00->30 x1 |
| 75 | 7E:5487 | 95.00 | 5/5 | 0/5 | unmentioned | 00->60 x4, 00->3C x1 |
| 76 | 7E:42FB | 90.00 | 5/5 | 0/5 | unmentioned | 70->D6 x3, 80->D6 x1, 70->00 x1 |
| 77 | 7E:2994 | 85.00 | 5/5 | 0/5 | unmentioned | 04->00 x2, 00->02 x1, 06->04 x1, 02->06 x1 |
| 78 | 7E:29BC | 85.00 | 5/5 | 0/5 | unmentioned | 04->00 x2, 00->02 x1, 06->04 x1, 02->06 x1 |
| 79 | 7E:2355 | 80.00 | 5/5 | 0/5 | unmentioned | 05->08 x1, 09->0A x1, 0B->0C x1, 0E->0F x1 |
| 80 | 7E:2357 | 80.00 | 5/5 | 0/5 | unmentioned | 05->08 x1, 09->0A x1, 0B->0C x1, 0E->0F x1 |
| 81 | 7E:238D | 80.00 | 4/5 | 0/5 | unmentioned | 00->90 x4 |
| 82 | 7E:28B2 | 80.00 | 4/5 | 0/5 | unmentioned | 00->FC x4 |
| 83 | 7E:28B3 | 80.00 | 4/5 | 0/5 | unmentioned | 00->FF x4 |
| 84 | 7E:2936 | 80.00 | 4/5 | 0/5 | unmentioned | 20->21 x4 |
| 85 | 7E:2CB0 | 80.00 | 4/5 | 0/5 | unmentioned | 00->01 x4 |
| 86 | 7E:3566 | 80.00 | 4/5 | 0/5 | unmentioned | 00->7F x4 |
| 87 | 7E:3567 | 80.00 | 4/5 | 0/5 | unmentioned | 00->FF x4 |
| 88 | 7E:356F | 80.00 | 4/5 | 0/5 | [~] Dungeon-Spawn-X \| Dungeon-Spawn: X 7E:356F / Y 7E:3571 | 00->11 x4 |
| 89 | 7E:3570 | 80.00 | 4/5 | 0/5 | unmentioned | 00->02 x4 |
| 90 | 7E:3574 | 80.00 | 4/5 | 0/5 | unmentioned | 00->46 x4 |
| 91 | 7E:53A2 | 80.00 | 4/5 | 0/5 | unmentioned | 00->D6 x4 |
| 92 | 7E:53A3 | 80.00 | 4/5 | 0/5 | unmentioned | 00->20 x4 |
| 93 | 7E:53A4 | 80.00 | 4/5 | 0/5 | unmentioned | 00->D8 x4 |
| 94 | 7E:53A5 | 80.00 | 4/5 | 0/5 | unmentioned | 00->20 x4 |
| 95 | 7E:53A6 | 80.00 | 4/5 | 0/5 | unmentioned | 00->D9 x4 |
| 96 | 7E:53A7 | 80.00 | 4/5 | 0/5 | unmentioned | 00->20 x4 |
| 97 | 7E:53A8 | 80.00 | 4/5 | 0/5 | unmentioned | 00->D8 x4 |
| 98 | 7E:53A9 | 80.00 | 4/5 | 0/5 | unmentioned | 00->20 x4 |
| 99 | 7E:53AA | 80.00 | 4/5 | 0/5 | unmentioned | 00->D9 x4 |
| 100 | 7E:53AB | 80.00 | 4/5 | 0/5 | unmentioned | 00->20 x4 |
