# Handover: AI Lufia II Player

Stand: 2026-08-09. Secret Skills Cave Räume 3 bis 5 sind live vermessen; das
Säulenrätsel in Raum 4 wurde durch Qwen live gelöst. Als Nächstes folgen die
dynamischen Pflichtgegner und die statische Geometrie von Raum 6.

## Harte Betriebsregeln

- Läuft ein `run_agent.py`-Prozess, den Codex nicht selbst gestartet hat, vor
  jedem Eingriff nachfragen. Weder Emulator noch Bridge oder Prozess ungefragt
  übernehmen oder stoppen.
- Keine zweite schreibende Steuerung parallel zu einem Agent-Run. Read-only
  Diagnose ebenfalls erst nach Klärung des Run-Besitzers.
- Secret-Skills-Cave-Ausnahme: Wurde ein Raum verlassen und danach `Reset`
  ausgeführt, ist die Rückkehr in den vorherigen Raum nicht mehr möglich.
  Deshalb nach einem Raumübergang niemals resetten, solange der Rückweg noch
  benötigt wird.
- Raumreset nur bei einem tatsächlich unlösbar gewordenen Rätsel. In Raum 4
  heißt das: Die Säule wurde an eine Wand geschoben und kann nicht mehr auf den
  Schalter gebracht werden. Unsicherheit, Kollision oder Stillstand reichen
  nicht.
- Resetfolge: Select einmal, Up einmal, Sanduhr/Reset mit A bestätigen. Nach
  Reset Wahrnehmung, Puzzlefortschritt und Intention vollständig neu aufbauen.
- Exploration darf Richtungen menschlich halten. Push: A halten, einen
  Richtungsimpuls geben und nach erreichter Zielposition loslassen.

## Bewiesene Live-Meilensteine

- Runs 41 und 42: Qwen aktivierte die Raum-3-Brücke, überquerte sie und
  erreichte reproduzierbar den westlichen Transit.
- Run 74 zeigte den Fehler der alten Raum-4-Sequenz: zuerst west schieben und
  erst am Ende nord führte in einen Loop.
- Run 75 bewies den einmaligen Nord-Push der Säule von `[8,21]` nach `[8,20]`,
  zeigte aber unzureichendes unmittelbares Feedback.
- Run 76 löste das Säulenrätsel live mit der korrigierten Reihenfolge:
  einmal nord, östlich um die Säule herum, anschließend west bis zum Schalter.
- Run 77 zeigte eine falsche Ausgangsannahme. Die Schwellen wurden anschließend
  gemeinsam per Live-Mesen-Aufnahme exakt vermessen.

## Secret Skills Cave: bestätigte Live-Koordinaten

### Raum 3

- Arrow firing position: `[28,24]`, west
- Brückenziel nach Aktivierung: `[21,26]`
- Westtür-Anker: `[17,23]`
- Brückensignal im Mapbuffer:
  - `(24,26)`: `02 -> 00`
  - `(24,27)`: `22 -> 02`
  - `(24,28)`: `20 -> 00`

### Raum 4: Säulenrätsel

- erster stabiler Raum-4-Tile: `[14,23]`
- Säulenanker ist immer der untere Fuß-/Basistile, nicht der obere Sprite-Tile
- initiale Säule: `[8,21]`
- Guy für den einmaligen Nord-Push: `[8,22]`
- Ergebnis des Nord-Pushs: Säule `[8,20]`
- Route auf die Ostseite: `[9,21] -> [9,20]`
- anschließend west schieben, bis die Säule den Schalter bei `[4,20]` belegt
- Guy darf niemals als Ersatzgewicht auf `[4,20]` gestellt werden
- bestätigte Raum-4-Ausgangsschwelle: `[6,17]`
- erster stabiler Raum-5-Entry: `[6,14]`

Nach erreichtem Schalter verschwinden die nur während des Schiebens verwendeten
temporären ASCII-Barrieren. Die Exitroute läuft über x=6 nach Norden; die alte
x=5-Annahme ist verworfen.

### Raum 5: Höhenwechsel und Transit

- Raum-5-Entry: `[6,14]`
- nördlicher Sprung: `[7,9] -> [8,11]`, Eingabe ost
- südlicher Sprung: `[7,10] -> [8,12]`, Eingabe ost
- Leiterfuß: `[13,12]`
- Leiterkopf: `[13,10]`
- Raum-5-Ausgangsschwelle: `[16,8]`, nord
- Transit-Eingang von Raum 5: `[16,6]`
- Transit-Ausgang zu Raum 6: `[19,6]`
- erster stabiler Raum-6-Entry: `[19,8]`

Die verifizierte U-Route lautet:

`[16,8] -> nord -> [16,6] -> ost -> [19,6] -> süd -> [19,8]`

Der Transit ist kein nummerierter Dungeonraum. Die exakte Entry-Verifikation
hat Vorrang vor überlappenden Bounds; `map_id` bleibt im gesamten Cave `5`.

Referenzaufnahmen liegen unter:

- `data/vision_observations/secret_skills_cave_room5/`
- `data/vision_observations/secret_skills_cave_room5_to_room6_transit/`
- `data/vision_observations/secret_skills_cave_room6/`

## Temporäres Puzzle-Overlay und Qwen-Feedback

- Das Overlay wird pro Entscheidung neu erzeugt und nicht dauerhaft als Karte
  gespeichert.
- Zeichen: `@` Actor-Füße, `P` beweglicher Anker, `S` Empfänger/Schalter, `T`
  nächste Actor-Position, `*` Objekt auf Empfänger, `#` temporäre Puzzlewand.
- Nach dem ersten Nord-Push erhält Qwen sofort natürlichsprachliches
  Erfolgsfeedback. Eine Wiederholung wird als `not_advised`, nicht als verboten,
  markiert und gilt nur für den exakt beobachteten Objektzustand.
- Ein Raumreset löscht Puzzlefortschritt und Intention; das Rätsel gilt wieder
  als ungelöst.

## Dynamische Dungeon-Gegner: bestätigtes Arbeitsmodell

Der Mapbuffer allein identifiziert keinen Gegner. Er zeigt nur eine
entity-agnostische Belegung, häufig `base -> base+1`. Die maßgebliche Quelle ist
die bestätigte Dungeon-Actor-Tabelle:

- Sprite-ID: `7E:05D2 + slot`
- Movement-State: `7E:066A + slot`
- Richtung: `7E:0692 + slot`
- Tile-X: `7E:06BA + slot`
- Tile-Y: `7E:06E2 + slot`
- Movement-Mode: `7E:070A + slot`
- 40 Slots `00..27`; `FF` bedeutet leer

Monster erhalten einen Zug, wenn Guy sich bewegt, das Schwert schwingt oder ein
Tool benutzt. Eine solche Aktion garantiert aber keinen Positionswechsel: Ein
Monster kann wiederholt gegen eine Wand laufen. Deshalb gilt:

- nur ein X/Y-Delta beweist tatsächliche Bewegung
- unverändertes X/Y bedeutet ausschließlich `position_changed=false`
- Movement-State/Richtung dürfen keinen erfolgreichen Schritt oder eine Wand
  behaupten
- der Mapbuffer bestätigt eine verschobene Belegung, ist aber nicht die
  Identitätsquelle
- Gegnerpositionen sind kurzlebige Laufzeitdaten und gehören nicht als feste
  Koordinaten in die Dungeon-Memory
- ein Pflichtgegner gilt erst nach korreliertem Kampfbeginn, gewonnenem Kampf
  und anschließend nicht mehr präsentem Overworld-Actor als besiegt

Die aktuelle read-only Raum-6-Baseline zeigte bewegungsaktive Kandidaten in
Slot 10/Sprite `83` bei `[28,6]` und Slot 11/Sprite `94` bei `[33,6]`. Diese
Slots sind noch nicht endgültig den beiden Pflichtgegnern zugeordnet; andere
geladene Actor-Slots können zu weiteren Cave-Räumen gehören.

## Verifikation

- Nach der Raum-4/5/6-Ankerkorrektur: 110 fokussierte Tests grün
  (`test_online_navigation_mapper`, `test_context_harness`,
  `test_modular_orchestrator`).
- Vollständiger Stand vor dem Checkpoint: 206 Tool-/Agent-Tests und 11
  WRAM-Discovery-Tests grün.
- Die exakten Raum-5-/Transitpunkte besitzen jeweils Screenshot und WRAM-Kontext.

## Unmittelbar als Nächstes

1. Einen kleinen read-only Dungeon-Actor-Decoder bauen, der pro Beobachtung
   `slot`, `sprite_id`, `current_live`, `previous_live`, `position_changed` und
   `present` liefert.
2. Die zwei Raum-6-Pflichtgegner visuell/semantisch einmal den Actor-Slots
   zuordnen und danach slotstabil verfolgen. Keine Bewegung pro Guy-Aktion
   voraussetzen.
3. Qwen nur die aktuell relevanten dynamischen Ziele und den Fortschritt
   `required/defeated/remaining` geben.
4. Raum 6 statisch weitervermessen: Abstiege, Leitern, Ausgang, Transit und
   Raum-7-Entry. Bewegliche Gegner nicht in die statische Karte schreiben.
5. Danach den Cave komplett durchlaufen und ein zweites Mal wiederholen.
6. `HANDOVER.md` und `CHANGELOG.md` nach erfolgreicher Live-Abnahme erneut
   aktualisieren; Commit und Push nur auf ausdrücklichen Auftrag.

## Projektlokale Modell-/GPU-Regel

- Aktuelle Baseline: `Qwen3-VL-4B-Spatial-Analysisv2.Q8_0.gguf` resident auf
  der RTX. Kein größeres Modell ohne reproduzierbaren Kapazitätsfehler.
- GPU-/Backend-Einstellungen gelten ausschließlich für diesen Workspace.
  Globale Ollama-, CUDA-, Vulkan- oder Systemeinstellungen nicht verändern.
- Modelle resident halten; kein Cold-Start pro Entscheidung.
- Der Watchdog meldet lange Denkpausen, bricht aber nicht blind hart ab.

## Kampfbedienung

- Initiale Aktionswahl im Kreuz: Richtung halten plus A.
- Danach Menüeintrag und Ziel jeweils einfach bestätigen.
- B im neutralen Aktionskreuz öffnet das Pre-Menu für Flucht/Positionswechsel.
- Battle-End-Screen: A menschlich lange halten, da EXP-/Level-Seiten variabel
  lang sein können.
