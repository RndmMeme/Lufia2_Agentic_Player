# Changelog

## 2026-08-06 — RTX-Spatial-Baseline und schlanker Exploration-Kontext

- Run 41 lieferte den ersten bestaetigten autonomen Qwen-Live-Durchgang durch
  Raum 3: Bruecke aktivieren, West-Kollision umgehen, Tueranker `(17,23)`
  erreichen und nach Norden in den sichtbaren Zwei-Tueren-Transitraum gehen.
  Kollisionen bleiben dafuer ueber reine Drehungen erhalten; erreichte
  Door/Exit-Landmarks exponieren ihre kuratierte Blickrichtung als
  datengetriebene Traversalaktion. Der noch faelschlich auf `room_3` stehende
  Mapperstatus ist ein separater Transit-Erkennungsfehler.
- Die beste bisherige Live-Leistung stammt von
  `Qwen3-VL-4B-Spatial-Analysisv2.Q8_0.gguf` auf der RTX, nicht von der Intel
  Arc. Run 29 erreichte in Raum 3 die Position zwei Tiles vor der linken Tür;
  Raum 4 wurde nicht betreten.
- Die Arc/Vulkan-Versuche mit groesserem Modell brauchten im Live-Betrieb mehr
  als 30 Sekunden pro Entscheidung und sind keine aktuelle Performance-Baseline.
  Das 4B-Spatial-Q8 bleibt daher das primaere Modell, bis ein reproduzierbares
  Kapazitaetsproblem ein groesseres Modell rechtfertigt.
- Ein fehlerhafter Raumgrenzen-Uebergang hatte den Schritt `(21,25)` nach
  `(20,25)` faelschlich als Raum 4 belohnt. Die Raum-3-Grenze und ein
  Regressionstest verhindern diese Fehlklassifikation; `map_id=5` bezeichnet
  den gesamten Cave/die eine Ebene, nicht seine internen Raeume.
- Exploration erhaelt jederzeit alle fuenf Dungeon-Werkzeuge mit Besitz-,
  Auswahl- und lokaler Relevanzinformation. Sie dienen sowohl Raetseln als auch
  dem Betaeuben/Umgehen von Gegnern. Das sonstige Vollinventar ist
  ausschliesslich per `retrieve(query='current inventory')` und hoechstens alle
  zehn Minuten abrufbar. `Buster Sword` ist kein Progressionsgegenstand;
  `Basement` wird intern eindeutig als `Basement key` normalisiert.
- Scenario-Keys bleiben Eingabe der internen Dungeon-Zugangslogik. Das Modell
  erhaelt daraus nur semantische erreichbare Orte und das naechste Ziel, keine
  Rohflags oder Liste fehlender Keys.
- Die zehnminuetige Vollinventar-Sperre gilt nur fuer Exploration. Im Kampf
  erhaelt die Aktionswahl kuratierte Makros der tatsaechlich vorhandenen
  Heil-, MP-, Revive-, Remedy-, Angriffs-, Kontroll-, Flucht-, Defense- und
  Buff-Items. Erst nach Wahl von `Item` werden alle besessenen, kampfnutzbaren
  Items als konkrete legale Optionen aus stabilen Storage-Slots angeboten.
- Normale Exploration-Entscheidungen koennen einen rollenden chronologischen
  Zwei-Frame-Kontext erhalten; bei einer gemeldeten Blockade ist ein drittes
  Bild konfigurierbar. Diese Option ist projektlokal und abschaltbar.
- Die persistente Mesen-Mailbox vermeidet nach dem ersten Windows-Lock-Fallback
  die erneute Zwei-Sekunden-Wartezeit pro Bridge-Anfrage.
- Verifikation: 132 Agent-Tests und 11 Bridge/WRAM-Tests bestanden.

## 2026-08-03 — Qwen3-VL-8B-Qualifikation

- Offizielles `Qwen3-VL-8B-Instruct` Q4_K_M und der zugehoerige Q8_0-mmproj
  wurden geladen und gegen die offiziellen SHA-256-Werte geprueft.
- Ein projektlokaler llama.cpp-Server haelt das VLM resident auf Vulkan0
  (Intel Arc A770): Kontext 12288, ein Slot, Q8-KV-Cache, Reasoning aus und
  mindestens 1024 Bildtokens. Globale Ollama- oder Systemeinstellungen bleiben
  unveraendert.
- Der Offline-Vertrag nutzt echte Secret-Skills-Cave-Frames und kuratierte
  WRAM-/Mapbuffer-Kontexte fuer Bruecke, Werkzeugwechsel, Dialog, Hoehenebenen,
  versteckten Buschschalter und Vasenraetsel.
- Der erste Lauf deckte zwei Testdefekte auf: ein zum WRAM-Kontext
  widerspruechliches Leiterbild und einen zu permissiven Vision-Scorer. Beide
  wurden korrigiert; ein fertiges, exakt ausgerichtetes Action-Landmark wird nun
  zudem deterministisch durch das Thinking Gate durchgesetzt.
- Finale Offline-Qualifikation: 22/22 Faelle ueber zwei Wiederholungen in
  `data/benchmarks/qwen3_vl_8b_qualification_v2.json`.
- Der erste Live-Smoke sendete keine Eingabe, weil die Mesen-Lua-Bridge schon
  beim Verbindungsaufbau nicht antwortete. Er wird nach Lua-Neustart mit maximal
  10 Aktionen wiederholt.

## 2026-08-03 — modularer Orchestrator (Arbeitsstand)

Dieser Abschnitt beschreibt den noch nicht committeten und noch nicht live
abgenommenen Refactoring-Stand.

### Modulgrenzen

- `context_builder.py` baut den rohen Modellkontext.
- `feedback_manager.py` besitzt Feedback, Reasoning-Evidence und die letzten
  Agent-Aktionen. Der Orchestrator greift ueber Properties auf genau diesen
  gemeinsamen Zustand zu.
- `model_gateway.py` kapselt Intent-, Vision- und Kampfaufrufe inklusive
  Watchdog und Thinking Gate.
- `battle_runner.py` kapselt die schrittweise Kampfsteuerung und wandelt auch
  Modell-Timeouts in einen kontrollierten Stop um.
- `action_executor.py` ist eine vorbereitete Modulgrenze. Sie bleibt erhalten,
  ist aber noch nicht an den Run-Loop angeschlossen.
- `dungeons/` enthaelt die gewuenschten Dungeon-Stubs. Nur
  `SecretSkillsCave` besitzt derzeit spezifische Live-Logik.

### Korrekturen waehrend des Reviews

- Der Watchdog protokolliert den echten Aktionszaehler, statt auf ein nicht
  vorhandenes `journal.actions` zuzugreifen.
- FeedbackManager und Orchestrator benutzen keinen getrennten Reasoning-State
  mehr.
- Dungeon-Erfolgsfeedback wird erst nach dem Bereinigen alter Evidence
  angehaengt und dadurch nicht sofort wieder geloescht.
- Die Bridge-Erkennung benutzt die in Mesen bewiesenen exakten Zustandsfolgen:
  aktiv `[00, 02, 00]`, inaktiv `[02, 22, 20]`.
- `select_tool` bleibt auch bei bereits ausgewaehltem Werkzeug verfuegbar,
  damit ein falsches Werkzeug gewechselt werden kann.
- Kontextkompression behaelt Karte, Reasoning-Evidence und die vollstaendige
  Aktionsliste. Das projektlokale Promptlimit liegt bei 10500 Zeichen.
- OpenAI-kompatible llama.cpp-Aufrufe erhalten ein korrekt eingepacktes
  JSON-Schema und rollenbezogene Tokenbudgets. Das Intent-Schema umfasst alle
  sieben Felder: `kind`, `direction`, `count`, `question`, `query`, `tool`,
  `rationale`.
- Visionaufrufe schlagen mit einer klaren Meldung fehl, wenn der geladene
  Server nur `completion` anbietet.

### Vorheriger Modellstand (historisch)

Der irrefuehrend benannte externe Start-Batch laedt aktuell tatsaechlich
`gemma-4-E4B-it-OBLITERATED-Q8_0` via llama.cpp/Vulkan. Der laufende Server
meldet nur Text-Completion; ohne multimodalen Projektor ist er kein VLM.

Ein synthetischer Drei-Schritt-Vertragstest waehlt nach der Promptkorrektur
`move west`, `move west`, `interact` fuer Bruecke, Bruecke und Westtuer. Das ist
ein Text-Semantiktest, kein Beweis fuer einen erfolgreichen Live-Cave-Lauf.

### Verifikation

- `python -m unittest discover -s tools -p "test_*.py"`: 97 Tests, gruen.
- `python -m unittest discover -s wram_discovery -p "test_*.py"`: 10 Tests,
  gruen.
- `python -m compileall -q agent tools`: erfolgreich.
- `git diff --check`: erfolgreich; nur erwartete LF/CRLF-Hinweise.

Der letzte als Erfolg bezeichnete Agent-Lauf war keiner: Er oszillierte in
Raum 3 und schoss wiederholt wirkungslos. Vor weiteren Architekturannahmen ist
ein kurzer kontrollierter Live-Smoke-Test erforderlich.
