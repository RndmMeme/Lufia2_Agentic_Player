# Handover: AI Lufia II Player

Stand: 2026-08-11. Secret Skills Cave Räume 3 bis 5 sind live vermessen; das
Säulenrätsel in Raum 4 wurde durch Qwen live gelöst. Ein begrenzter
20-Stunden-Supervisor mit Continual Harness, Loop-Erkennung und read-only
Slot-3-Recovery ist implementiert und live verifiziert.

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
- Vollständiger Stand nach dem kompletten Continual-Harness-Flow: 230
  Tool-/Agent-Tests und 11 WRAM-Discovery-Tests grün.
- Die exakten Raum-5-/Transitpunkte besitzen jeweils Screenshot und WRAM-Kontext.
- Long-Session-Recovery: 244 Tool-/Agent-Tests und 12 WRAM-Tests grün.
- Mesen-Bridge-Protokoll 4 lud den manuell kuratierten Slot 3 live read-only.
  Drei WRAM-Snapshots waren stabil bei Map 5, `[28,55]`, Exploration.
- Slot 3 blieb bytegenau unverändert: 178748 Bytes, SHA-256
  `7b2ff14affce83441786355d2db8151c95a21958b3872b91756f04d1fd496e3d`.

## Unbeaufsichtigter 20-Stunden-Betrieb

- Einstieg: `start_long_learning_session.bat` prüft/startet den lokalen
  CUDA-Modellserver, prüft die Lua-Bridge und startet den Supervisor.
- Qwen besitzt keinerlei Save-/Load-Intent. Recovery liegt ausschließlich im
  Supervisor.
- Raumreset wird nur bei einem persistierten kuratierten
  `room_reset_recovery.eligible=true` verwendet.
- Ansonsten lädt die Bridge ausschließlich den festen Mesen-Slot 3. Sie besitzt
  kein Capture-/Save-Kommando und benutzt Slot 4 nicht.
- Der Supervisor fixiert Pfad, Größe und SHA-256 des Ankers beim Start und
  prüft sie vor jedem Reload erneut.
- Recovery wird durch wiederholte lokale Kanten/Blockaden ohne neue Evidenz,
  mehrere unveränderte Zyklen, einen hängenden Child-Prozess oder einen nicht
  fortsetzbaren Agent-Stop ausgelöst. Danach beginnt eine neue Episode; der
  globale Continual-Harness-State bleibt erhalten.
- Normaler manueller Stop: `start_long_learning_session.bat --stop`. Die
  Anforderung wird zwischen abgeschlossenen Aktionen und nochmals direkt nach
  einem Modellaufruf vor der nächsten Controlleraktion geprüft.
- Status: `start_long_learning_session.bat --status`. `Ctrl+C` ist der
  sofortige Notausgang; der Supervisor beendet den Child zuerst kontrolliert
  und erzwingt das Ende nur nach 15 Sekunden.
- Ein workspace-globaler Supervisor-Lock und der Mesen-Controller-Lock
  verhindern parallele schreibende Sessions. Aktive Child-PIDs werden in
  `session_state.json` geführt und vor jedem neuen Batch-Start geprüft.
- Mehrere parallele Mesen-Instanzen werden derzeit bewusst nicht unterstützt:
  Bridge-Mailbox, Controller-Lock und Modellserver-Slot sind single-owner.

## Unmittelbar als Nächstes

### Continual-Harness-Einführung (implementiert)

Die ursprüngliche Implementierungsreihenfolge ist abgeschlossen und bleibt als
Entscheidungsprotokoll erhalten.

1. `shadow` als einzigen initialen Modus einführen. Der Refiner darf
   Trajektorien lesen und versionierte Vorschläge schreiben, aber weder den
   aktiven Prompt noch Python, kuratierte Memory oder Controlleraktionen ändern.
2. Als Eingabe nur vorhandene Run-Artefakte verwenden: `journal.jsonl`,
   `action_outcomes.jsonl`, `short_term_memory.json`, Promptstatistik sowie
   referenzierte Keyframes. Daraus ein begrenztes jüngstes Trajektorienfenster
   bilden; keine komplette Run-Historie in jeden Refiner-Aufruf kopieren.
3. Harness-State in vier getrennte Vorschlagsbereiche schreiben:
   `prompt_overlay`, `memory`, `skills`, `subagents`. Jeder Vorschlag benötigt
   Quelle/Schrittbereich, Evidenz, Scope, erwarteten Nutzen und
   Rücknahmebedingung.
4. Sub-Agents zunächst als Spezifikationen desselben residenten Modells
   behandeln: eigener Systemprompt, Tool-Allowlist, Turn-Limit, Rückgabeschema
   und Return-Condition. Keine parallele Emulatorsteuerung und kein zusätzlich
   geladenes Modell voraussetzen.
5. Skills zunächst deklarativ halten. Nur bestehende allowlistete Controller-
   Aktionen zusammensetzen und Erfolg über WRAM/Postconditions prüfen; keinen
   frei generierten Python-Code ausführen.
6. Refiner ereignisbasiert auslösen: echter Loop/Stall, Reasoning-Limit,
   abgeschlossener Raum/Puzzle/Kampf oder expliziter Aufruf. Nicht nach jeder
   einzelnen Eingabe und niemals mitten in einer unvollständigen Controller-
   Sequenz.
7. Shadow-Vorschläge gegen historische Runs und Tests auswerten. Erst nach
   nachvollziehbar hilfreichen, schema-validen Ergebnissen einen separaten
   `gated`-Modus bauen. Der unveränderliche Kernprompt, kuratierte Fakten und
   Secret-Cave-Resetregeln bleiben auch dann schreibgeschützt.
8. Optional später einen stärkeren Refiner (lokal auf der Arc oder über Prime
   Intellect/API) anbinden. Actor und Refiner bleiben provider-neutral; das
   langsame eGPU-Modell läuft nur zwischen Meilensteinen, nicht pro Bewegung.

Geplante minimale Modulgrenze:

```text
agent/adaptation/
  trajectory_window.py   # begrenzte, normalisierte Run-Evidenz
  harness_state.py       # versionierte Shadow-Vorschläge
  refiner.py             # strukturierter Modellaufruf
  validator.py           # Schema, Scope, Allowlist und Immutable-Kernel
```

Run-Konfiguration: `disabled` bleibt Default; Aktivierung ausschließlich über
einen expliziten projektlokalen CLI-/Config-Schalter. Jeder Refiner-Aufruf muss
in `harness_evolution.jsonl` protokolliert und ohne Emulatoraktion abbrechbar
sein.

Implementierungsstand 2026-08-11:

- Der provider-neutrale Shadow-Refiner liegt in `agent/adaptation/` und wird nur
  mit `--enable-harness-refiner` aktiviert. Ohne den Schalter entstehen keine
  Harness-Artefakte.
- Auslöser sind abgeschlossene Meilensteine/Modus- oder Raumwechsel, erkannte
  Navigationsloops, wiederholter Stillstand und explizite Abbruchgründe. Der
  Aufruf erfolgt nur zwischen abgeschlossenen Aktionen, nie mitten in einer
  Controllersequenz.
- Vorschläge werden ausschließlich als inaktive Generationen unter
  `<run-dir>/harness_evolution/generation_NNNN.json` und zusätzlich in
  `<run-dir>/harness_evolution.jsonl` geschrieben. Modell- und Schemafehler
  bleiben auf diesen Nebenpfad begrenzt und stoppen das Spiel nicht.
- Skills sind deklarative Folgen bereits freigegebener Intents; frei erzeugter
  Code und `reset_room` sind ausgeschlossen. Sub-Agent-Vorschläge dürfen nur
  analysieren und einen Intent empfehlen, nicht den Emulator steuern.
- Ein isolierter realer Smoke-Test gegen
  `Qwen3-VL-4B-Spatial-Analysisv8-Q8_0.gguf` auf CUDA bestand Schema und
  Validator. Das Modell erkannte die synthetische A-B-A-B-Navigationsschleife
  korrekt und gab konservativ keine unbelegte Änderung aus. Mesen wurde dabei
  nicht angesprochen.
- Der anschließende vollständige Live-Smoke
  `data/runs/harness_shadow_live_smoke_02/live` bewies auch die
  Orchestrator-Integration: eine WRAM-bestätigte `face west`-Aktion löste
  `model_wait_loop` aus; `generation_0001.json` blieb mit `active: false` und
  `status: proposed_not_applied` inert. Position, Raum und Puzzle blieben
  unverändert. Smoke 01 war absichtlich folgenlos, weil Guy bereits nach Osten
  blickte und das Thinking Gate die redundante Aktion korrekt verwarf.
- Die dabei gefundene llama.cpp-Inkompatibilität mit großen JSON-Schema-
  `maxLength`-Grammatiken ist behoben: Der Provider erhält keine Stringlimits;
  `HarnessProposalValidator` erzwingt weiterhin alle bisherigen Grenzen.
- Der vollständige Gated-Lifecycle liegt in `agent/adaptation/manager.py` und
  `global_store.py`: runübergreifende Kandidaten, standardmäßig zwei getrennte
  Bestätigungsruns, aktive Canaries, Add/Update/Retire per stabiler `target_id`,
  per-Action-Wirkungsmessung und automatischer Rollback.
- `--enable-harness-gated` aktiviert den vollständigen Flow;
  `--harness-state-path` isoliert A/B- und Smoke-Landschaften. Shadow-Runs sehen
  vorhandene aktive Canaries ausdrücklich nicht.
- Gelernte Prompt-Overlays, Memories und deklarative Skills erscheinen nur im
  niedrig priorisierten `learned_harness`-Kontext. Runtime-Subagents sind
  getrennte Aufrufe desselben residenten Modells, dürfen nur read-only
  `look`/`look_map`/`retrieve` anfragen und liefern normalisierte Empfehlungen.
- Der isolierte Gated-Mesen-Smoke
  `data/runs/harness_gated_live_smoke_01` bestätigte echte Action-Evidenz,
  Kandidatensammlung und `active: 0`. Dabei erkannte Validator-Hardening
  unzulässige Scope-Namen und Thinking-Gate-Umgehungssprache; beides wird nun
  vor dem globalen Kandidatenstore verworfen.
- Bedienung und Sicherheitsgrenzen stehen in `docs/continual_harness.md`;
  `tools/harness_control.py` zeigt Status/Review-Queue und ermöglicht explizite
  Promotion oder Rollback.

### Gameplay-Arbeit

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
6. Den kompletten Cave erneut live laufen lassen und die Recovery-Logs unter
   `data/runs/long_*/supervisor.jsonl` auf zu frühe Resets prüfen.
7. Commit und Push nur auf ausdrücklichen Auftrag.

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
