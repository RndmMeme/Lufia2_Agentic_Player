# Handover: AI Lufia II Player

Stand: 2026-08-06, reproduzierbarer Raum-3-Live-Erfolg.

## Letzter dokumentierter Live-Zustand

- Run 42 endete wie Run 41 bei `(17,20)`, Blickrichtung Nord, im sichtbaren
  Zwei-Tueren-Transitraum. Der Mapper bezeichnet ihn noch faelschlich als
  `room_3`, weil `map_id=5` unveraendert bleibt.
- Die Bruecke wurde erfolgreich aktiviert und durchquert.
- Run 42 stoppte kontrolliert am Zeitlimit; kein Agent-Run sollte derzeit aktiv
  sein. Vor einem neuen Run trotzdem nur lesend pruefen.
- Niemals parallel zum Runner eine zweite File-Bridge-Abfrage starten; das erzeugte bereits eine `request.tmp`-Race.
- Der begrenzte Qwen-Live-Smoke hat keine Eingabe gesendet: Die Lua-Bridge war
  bereits beim Verbindungsaufbau nicht mehr erreichbar. Nach einem Lua-Neustart
  denselben Lauf mit maximal 10 Aktionen wiederholen.

## Gerade bewiesenes Mapbuffer-Signal

Action Outcome 64 in `data/runs/qwen_cave_probe_01/action_outcomes.jsonl` beweist beim ersten `use_tool`:

- live `(24,26)`, Adresse `0x45FC`: `02` (hole_or_gap) -> `00` (plain_floor)
- live `(24,27)`, Adresse `0x4636`: `22` (unknown) -> `02` (hole_or_gap)
- live `(24,28)`, Adresse `0x4670`: `20` (alternate_floor) -> `00` (plain_floor)
- `semantic_count=3`, danach bei weiteren Pfeilschuessen jeweils `semantic_count=0`

Das ist das eindeutige Erfolgssignal fuer die geschaltete Bruecke. Keine Vision-Heuristik dafuer verwenden.

## Orchestrator-Refactoring (integriert, noch nicht live abgenommen)

### Ziel-Architektur

```
agent/
  orchestrator.py          -> nur Run-Loop + Koordination (~350 Zeilen)
  context_builder.py       -> _context(), Kontext-Kompaktierung
  model_gateway.py         -> _ask_model(), _look(), _look_map(), _ask_battle_model()
  action_executor.py       -> vorbereitete Aktionsgrenze; noch nicht vom Run-Loop benutzt
  feedback_manager.py      -> _remember_action(), _clear_reasoning(), Feedback-Ledger
  battle_runner.py         -> Battle-Loop (extrahiert aus orchestrator)
  dungeons/                -> BaseDungeon, SecretSkillsCave, 28 weitere Stubs
```

### Abhaengigkeiten

```
orchestrator.py
  -> context_builder.py
  -> feedback_manager.py
  -> model_gateway.py
  -> battle_runner.py
  -> dungeons/

`action_executor.py` bleibt als gewuenschte Modulvorbereitung erhalten, ist
aber noch nicht verdrahtet. Das ist kein bewiesener aktiver Bestandteil.
```

### Dungeon-Module (29 Stubs mit korrekten map_ids aus zones.txt)

| map_id | Dungeon | Datei |
|--------|---------|-------|
| 5 | Secret Skills Cave | `secret_skills_cave.py` |
| 6 | Sundletan Cave | `cave_to_sundletan.py` |
| 10 | Lake Cave | `lake_cave.py` |
| 15 | Alunze Castle | `alunze_castle_basement.py` |
| 24 | Alunze Cave | `alunze_northwest_cave.py` |
| 30 | Tanbel Tower | `tanbel_southeast_tower.py` |
| 39 | Ruby Cave | `ruby_cave.py` |
| 48 | Treasure Sword Shrine | `treasure_sword_shrine.py` |
| 55 | Gordovan Tower | `gordovan_west_tower.py` |
| 64 | Cave Bridge | `cave_to_bound_kingdom.py` |
| 75 | Ancient Tower | `ancient_tower.py` |
| 96 | Phantom Tree Mountain | `phantom_tree_mountain.py` |
| 108 | Tower of Sacrifice | `tower_of_sacrifice.py` |
| 117 | Karlloon Shrine | `karlloon_north_shrine.py` |
| 126 | Flower Mountain | `flower_mountain.py` |
| 140 | Dankirk Dungeon | `dankirk_north_dungeon.py` |
| 163 | Mountain of No Return | `mountain_of_no_return.py` |
| 168 | Divine Shrine | `divine_shrine.py` |
| 174 | Shrine of Vengeance | `shrine_of_vengeance.py` |
| 183 | Tower of Truth | `tower_of_truth.py` |
| 192 | Dragon Mountain | `dragon_mountain.py` |
| 209 | Gratze Castle | `gratze_castle.py` |
| 218 | Shuman Tower | `shuman_tower.py` |
| 222 | Strahda Tower | `strahda_tower.py` |
| 226 | Kamirno Tower | `kamirno_tower.py` |
| 230 | Daos Shrine | `daos_shrine.py` |

**Hinweis:** Sundletan Cave hat zwei Ebenen: `06` (erste Ebene) und `07` (zweite Ebene). Der Stub `cave_to_sundletan.py` hat `map_id=6`.

## Zuletzt implementiert

- `agent/navigation/online_mapper.py`
  - State besitzt jetzt `completed_landmarks`.
  - `record_action_landmark_effect(...)` schliesst ein Landmark nur ab, wenn Aktion, exakte Fussposition und erforderliche Blickrichtung passen UND der Mapbuffer mindestens eine semantische Tile-Aenderung zeigt.
  - `current_room_context()` liefert `completed` und `completion_evidence`.
- `agent/context_harness.py`
  - Thinking Gate blockiert das Verlassen eines bereits abgeschlossenen Action-Landmarks nicht mehr.
- `agent/orchestrator.py`
  - `_remember_action()` uebergibt Tile-Diffs an den Mapper und speichert Landmark-Abschluesse sofort im Navigation-Graphen.
- `agent/intent.py`
  - Striktes Intent-Schema mit `kind`, `direction`, `count`, `question`,
    `query`, `tool`, `rationale`; keine unbelegten Aliasfelder.
- `agent/dungeons/` — Dungeon-spezifische Feedback-Logik (BaseDungeon, SecretSkillsCave mit Brücken-Logik)
- `runtime_config.json` — projektlokaler OpenAI-kompatibler llama.cpp-Provider auf Port 8080
- `tools/test_intent_parsing.py` — 8 Intent-Parsing-Tests
- `tools/test_sanduhr_reset_diff.py` — Mapbuffer-Diff-Test für Sanduhr-Reset und Pfeilschuss
- `tools/test_modular_orchestrator.py` — fokussierte Regressionstests fuer
  Toolwechsel, Bridgewerte, Watchdog, JSON-Schema und Room-3-Navigation
- `tools/create_dungeon_stubs.py` — 28 Dungeon-Stubs aus `emulator/maps/Dungeons/`
- `tools/update_dungeon_map_ids.py` — map_ids aus `zones.txt` in die Stubs eintragen

## Test-Ergebnisse

- **132/132 Tool-Tests** gruen
- **11/11 WRAM-Discovery-Tests** gruen
- **8/8 einfache Intent-Parsing-Checks** — strikte Kinds, Richtungen und
  `count: null`; keine behauptete Alias-Kompatibilitaet
- Der als Erfolg bezeichnete Live-Run war **kein Cave-Fortschritt**: 20 Aktionen,
  Oszillation zwischen `(27,25)` und `(28,25)`, zehn wirkungslose Pfeilschuesse,
  Ende durch Action-Limit. Nicht als Modellnachweis verwenden.
- Historischer Text-only-Drei-Schritt-Vertragstest des E4B nach der
  Promptkorrektur: `move west`, `move west`, `interact` fuer Bruecke, Bruecke
  und Westtuer. Ein separater Landmark-Test waehlt bei unfertiger Bruecke
  korrekt `use_tool`. Das beweist nur isolierte Intentsemantik, noch keine
  Live-Navigation.
- Run 30 blieb wegen eines Harness-Fehlers stehen: `$1272` enthielt noch die
  letzte Kollisionsrichtung und wurde beim neuen Runner faelschlich als aktuell
  blockierte Richtung ausgegeben. Gleichzeitig blieb `look` im unveraenderten
  Zustand unbegrenzt verfuegbar.
- Der Fix ist live bestaetigt: Blockierung wird nur noch kausal nach einem
  unmittelbar fehlgeschlagenen Move ausgegeben; `look`/`look_map` jeweils nur
  einmal pro unveraendertem Zustand. Run 31 bewegte Qwen in zwei Entscheidungen
  `(28,30) -> (28,29) -> (28,28)` in 6.391 Sekunden.
- Die rekonstruierte Raum-3-Referenzroute, Fehleranalyse und der kompakte
  Imitationsentwurf stehen in `docs/room3_spatial_imitation_analysis.md`.
- Run 30 enthaelt drei an denselben Ordner angehaengte Sessions. Die ersten
  beiden endeten ohne Eingabe in LOOK-Schleifen. Die dritte absolvierte 16
  Emulatoraktionen bis `(23,26)` und endete erst nach zehn vom Gate abgelehnten
  weiteren LOOK-Wuenschen. `reasoning_step_limit` bedeutet 12 aufeinanderfolgende
  Wahrnehmungs-/Retrieval-/abgelehnte Entscheidungen ohne bestaetigten
  Emulatorfortschritt; es ist weder Tokenlimit noch Denkzeitlimit.
- Der Livekontext trennt nun `ACTOR_LOCAL_3X3` um die Figur und einen nach
  erfolgreicher Weltaktion eingefrorenen `POST_ACTION_EFFECT_REGION`-3x3 am
  entfernten Wirkungsort. PREVIOUS/CURRENT plus WRAM-Tilewechsel bilden damit
  die menschliche Wahrnehmungskette ab.
- **Runs 41 und 42 bestaetigen reproduzierbar den Qwen-Live-Erfolg fuer Raum
  3:** Das
  RTX-Spatial-Q8 aktivierte die Bruecke, fand nach den West-Kollisionen den
  Nordumweg, erreichte den Tueranker `(17,23)` und ging anschliessend dreimal
  nach Norden in den sichtbaren Zwei-Tueren-Transitraum. Run 42 endete wie Run
  41 bei `(17,20)`; damit ist der Durchgang kein Einzelerfolg. Zwei kleine,
  allgemeine
  Kontextkorrekturen waren dafuer noetig: Eine bestaetigte Kollision bleibt
  ueber reines Drehen am selben Ort erhalten, und ein erreichtes Door/Exit-
  Landmark exponiert `move <facing>` als Traversalaktion.
- Der Mapper hielt den Zustand danach trotzdem faelschlich auf `room_3`, weil
  `map_id=5` unveraendert bleibt und sich interne Raumkoordinaten ueberlappen.
  Der aktuelle Screenshot ist der Erfolgsbeweis; die automatische
  Transit-Erkennung ist der naechste getrennte Fehler.

## Unmittelbar als Naechstes

1. Den sichtbaren Transitraum trotz unveraendertem `map_id=5` und
   ueberlappenden Koordinaten automatisch erkennen; den Room-3-Erfolg nicht aus
   Bounds allein ableiten.
2. Den Zwei-Tueren-Transitraum und Raum 4 als naechstes einzelnes
   Ziel behandeln; keine weitere Cave-Route vorgeben.
3. Erst nach einem echten wiederholten Stall genau einen Hinweis, Micro-Map-
   Ausschnitt oder Referenzpose eskalieren.

## Danach noch offen

- Normales Action-Limit darf einen laufenden Kampf nicht mitten in Aktions- oder Zielauswahl stranden. Kampf bis Ende/Result-Screen innerhalb `max_battle_inputs` kontrolliert zu Ende fuehren.
- Battle-End-Screen: A menschlich lange halten, weil EXP/Level-Seiten variabel lang sind.
- Secret Skills Cave einmal komplett beenden und danach ein zweites Mal vom Start wiederholen. Vorher keine Ausweitung auf andere Dungeons oder Overworld.
- Lessons Learned weiterhin strikt trennen:
  - global anwendbare Spiel-/Navigationsregeln
  - ausschliesslich Secret-Skills-Cave-spezifische Hinweise
- Room-3-Brueckensignal spaeter als kuratierte map-spezifische Semantik dokumentieren.
- 28 Dungeon-Stubs implementieren (derzeit nur `SecretSkillsCave` mit Brücken-Logik).

## Projektlokale Modell-/GPU-Regel

- GPU-/Backend-Auswahl gilt ausschliesslich fuer diesen Workspace/use case.
- Keine globalen Ollama- oder System-Einstellungen aendern.
- Globales Ollama auf `127.0.0.1:11434` und andere Anwendungen unangetastet lassen.
- Aktuelle Live-Baseline: `Qwen3-VL-4B-Spatial-Analysisv2.Q8_0.gguf`, resident
  auf der RTX. Runs 41 und 42 absolvierten Raum 3 bis in den sichtbaren
  Transitraum und endeten beide bei `(17,20)`.
  Run 29 bleibt der historische Vorlaeufer, der zwei Tiles vor der linken Tuer
  endete.
- Der offizielle `Qwen3-VL-8B-Instruct` Q4_K_M plus Q8-mmproj bleibt ein
  historisch offline qualifizierter Kandidat (22/22), aber Arc/Vulkan brauchte
  live mehr als 30 Sekunden pro Entscheidung. Diese Zeiten duerfen nicht Run 29
  zugeschrieben werden.
- Vorerst kein groesseres Modell: Erst ein reproduzierbarer semantischer Fehler
  bei korrektem WRAM-, Karten- und Bildkontext rechtfertigt den Wechsel. Die
  bisherigen Live-Probleme waren ueberwiegend Kontext- und Raumzuordnungsfehler.
- GPU-/Backend-Startparameter bleiben projektlokal; keine globalen Ollama-,
  Vulkan-, CUDA- oder Systemeinstellungen aendern. Modelle bleiben resident.
- `start_project_qwen3_vl_vulkan.ps1` dokumentiert weiterhin nur den separaten
  Arc/8B-Versuch und ist nicht der Startweg der aktuellen RTX-Spatial-Baseline.

## Wichtige Bedienregeln

- Exploration darf Richtungen menschlich halten; nicht tap-by-tap erzwingen.
- Kampf: Initiale Aktionsauswahl im Kreuz benoetigt Richtung halten plus A. Danach Auswahl und Ziel jeweils einfache Bestaetigung.
- B im neutralen Aktionskreuz geht zum Pre-Menu fuer Flucht/Positionswechsel.
- Raumreset: Select einmal, Up einmal, Reset/Sanduhr mit A ausfuehren; humanoide Eingabetimings.
- Ein besiegtes normales Monster respawnt durch Raumreset; Bossmonster nicht.
