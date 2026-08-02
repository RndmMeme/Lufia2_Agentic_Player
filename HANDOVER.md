# Handover: AI Lufia II Player

Stand: 2026-08-02, pausiert auf ausdruecklichen Wunsch des Users.

## Unmittelbarer Live-Zustand

- Mesen steht in Secret Skills Cave, Raum 3.
- Letzte bekannte Figurposition: `(28,24)`, Blickrichtung West.
- Pfeil ist ausgewaehlt.
- Der Pfeilschalter wurde erfolgreich getroffen und die Bruecke ist aktiv.
- Kein Agent-Run sollte derzeit aktiv sein. Vor einem neuen Run trotzdem nur lesend pruefen.
- Niemals parallel zum Runner eine zweite File-Bridge-Abfrage starten; das erzeugte bereits eine `request.tmp`-Race.

## Gerade bewiesenes Mapbuffer-Signal

Action Outcome 64 in `data/runs/qwen_cave_probe_01/action_outcomes.jsonl` beweist beim ersten `use_tool`:

- live `(24,26)`, Adresse `0x45FC`: `02` (hole_or_gap) -> `00` (plain_floor)
- live `(24,27)`, Adresse `0x4636`: `22` (unknown) -> `02` (hole_or_gap)
- live `(24,28)`, Adresse `0x4670`: `20` (alternate_floor) -> `00` (plain_floor)
- `semantic_count=3`, danach bei weiteren Pfeilschuessen jeweils `semantic_count=0`

Das ist das eindeutige Erfolgssignal fuer die geschaltete Bruecke. Keine Vision-Heuristik dafuer verwenden.

## Zuletzt implementiert

- `agent/navigation/online_mapper.py`
  - State besitzt jetzt `completed_landmarks`.
  - `record_action_landmark_effect(...)` schliesst ein Landmark nur ab, wenn Aktion, exakte Fussposition und erforderliche Blickrichtung passen UND der Mapbuffer mindestens eine semantische Tile-Aenderung zeigt.
  - `current_room_context()` liefert `completed` und `completion_evidence`.
- `agent/context_harness.py`
  - Thinking Gate blockiert das Verlassen eines bereits abgeschlossenen Action-Landmarks nicht mehr.
- `agent/orchestrator.py`
  - `_remember_action()` uebergibt Tile-Diffs an den Mapper und speichert Landmark-Abschluesse sofort im Navigation-Graphen.
- `tools/test_online_navigation_mapper.py`
  - Test fuer semantisch bewiesenen Landmark-Abschluss hinzugefuegt.
- Zieltests ausgefuehrt:
  - `python -m unittest tools.test_online_navigation_mapper tools.test_context_harness`
  - Ergebnis: 20 Tests, OK.
- Der bereits erfolgte historische Pfeilschuss wurde in
  `data/runs/qwen_cave_probe_01/online_navigation_graph.json`
  als abgeschlossenes Landmark `room_3:arrow_firing_position` eingetragen.

## Unmittelbar als Naechstes

1. Nur lesend kontrollieren, dass kein alter `run_agent.py`-Prozess aktiv ist.
2. Den kompletten Testbestand laufen lassen (bisher nach dem letzten Patch nur die 20 Zieltests):
   `python -m unittest discover -s tools -p "test_*.py"`
   Danach bei Bedarf auch die aktiven Tests unter `wram_discovery`.
3. Den bestehenden Run `data/runs/qwen_cave_probe_01` fortsetzen, nicht neu beginnen.
4. Erwartetes Verhalten: Qwen muss das abgeschlossene Pfeil-Landmark verlassen, westlich ueber die nun aktive Bruecke zu `(21,26)` und danach zur Westtuer bei `(17,23)` navigieren.
5. Journal und `action_outcomes.jsonl` waehrend des Runs beobachten, aber keine zweite Bridge-Verbindung oeffnen.
6. Wenn das Modell trotz `completed=true` erneut schiesst, den kompakten LLM-Kontext und Prompt pruefen: Completion muss sichtbar sein und die Anweisung muss lauten, zum naechsten Erfolgsziel weiterzugehen.

## Danach noch offen

- Normales Action-Limit darf einen laufenden Kampf nicht mitten in Aktions- oder Zielauswahl stranden. Kampf bis Ende/Result-Screen innerhalb `max_battle_inputs` kontrolliert zu Ende fuehren.
- Battle-End-Screen: A menschlich lange halten, weil EXP/Level-Seiten variabel lang sind.
- Secret Skills Cave einmal komplett beenden und danach ein zweites Mal vom Start wiederholen. Vorher keine Ausweitung auf andere Dungeons oder Overworld.
- Lessons Learned weiterhin strikt trennen:
  - global anwendbare Spiel-/Navigationsregeln
  - ausschliesslich Secret-Skills-Cave-spezifische Hinweise
- Room-3-Brueckensignal spaeter als kuratierte map-spezifische Semantik dokumentieren.

## Projektlokale Modell-/GPU-Regel

- GPU-/Backend-Auswahl gilt ausschliesslich fuer diesen Workspace/use case.
- Keine globalen Ollama- oder System-Einstellungen aendern.
- Projektlokaler Ollama-Endpunkt: `127.0.0.1:11435`.
- `start_project_ollama_cuda.ps1` setzt Variablen nur fuer seinen Kindprozess.
- Globales Ollama auf `127.0.0.1:11434` und andere Anwendungen unangetastet lassen.
- Modell resident halten (`keep_alive=-1`), keine Modell-Swaps pro Entscheidung.
- Aktuell alle Rollen: `qwen3-vl:4b`, Kontext 4096, Prompt-Limit 9000 Zeichen.

## Wichtige Bedienregeln

- Exploration darf Richtungen menschlich halten; nicht tap-by-tap erzwingen.
- Kampf: Initiale Aktionsauswahl im Kreuz benoetigt Richtung halten plus A. Danach Auswahl und Ziel jeweils einfache Bestaetigung.
- B im neutralen Aktionskreuz geht zum Pre-Menu fuer Flucht/Positionswechsel.
- Raumreset: Select einmal, Up einmal, Reset/Sanduhr mit A ausfuehren; humanoide Eingabetimings.
- Ein besiegtes normales Monster respawnt durch Raumreset; Bossmonster nicht.

