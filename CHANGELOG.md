# Changelog

## 2026-08-11 — Read-only Slot-3-Recovery und 20-Stunden-Supervisor

- `agent/session_supervisor.py` startet begrenzte, fortsetzbare Agent-Zyklen
  über bis zu 20 Stunden und hält den Continual Harness runübergreifend aktiv.
- Echte lokale Bewegungsloops werden aus wiederholten Kanten, Blockaden und
  negativen Outcomes ohne Checkpoint/Weltänderung erkannt. Zyklusübergreifender
  Stillstand bleibt als zweite Erkennungsebene erhalten.
- Recovery bevorzugt nur einen kuratiert erlaubten Raumreset. Andernfalls wird
  der manuell geprüfte Mesen-Slot 3 geladen; Child-Timeouts und nicht
  fortsetzbare Agent-Stops beenden die Langzeit-Session nicht mehr hart.
- Die Lua-Bridge wurde auf Protokoll 4 angehoben. Capture-/Save-Kommandos und
  `emu.createSavestate` wurden entfernt. Slot 4 wird nicht verwendet.
- Pfad, Größe und SHA-256 des Slot-3-Ankers werden beim Start fixiert und vor
  jedem Reload geprüft. Eine während der Session veränderte Datei wird nicht
  geladen.
- `start_long_learning_session.bat` verbindet Modellserver-Start,
  Bridge-Diagnose und den 20-Stunden-Lauf in einem manuell wiederholbaren
  Einstiegspunkt.
- Der Starter unterstützt `--status`, `--stop` und `--check`. Kooperativer
  Stop wird zwischen Aktionen sowie nach einem Modellaufruf vor neuer Eingabe
  erkannt; `Ctrl+C` bleibt der forcierte Notausgang.
- Ein zusätzlicher workspace-globaler Supervisor-Lock verhindert auch zwischen
  Agent-Zyklen zwei Long-Session-Prozesse. Child-PIDs werden persistiert; der
  Start-Preflight verlangt sowohl freien Supervisor- als auch freien
  Mesen-Controller-Lock.
- Parallele Mesen-Instanzen bleiben explizit außerhalb des aktuellen Designs;
  Bridge-Mailbox, Controller und der residente Modellslot sind single-owner.
- Live verifiziert: Slot 3 wurde read-only geladen; drei WRAM-Snapshots waren
  identisch bei Map 5, `[28,55]`, Exploration. Die Datei blieb unverändert bei
  178748 Bytes und SHA-256
  `7b2ff14affce83441786355d2db8151c95a21958b3872b91756f04d1fd496e3d`.
- Verifiziert: 244 Tool-/Agent-Tests und 12 WRAM-Discovery-Tests grün;
  `git diff --check` ohne Fehler.

## 2026-08-11 — Continual-Harness Shadow und Gated Mode

- Ein provider-neutraler, evidenzbasierter Shadow-Refiner kann über
  `--enable-harness-refiner` explizit zugeschaltet werden; Default bleibt
  deaktiviert und der aktive Actor-Prompt wird nicht verändert.
- Der Refiner nutzt begrenzte Ausschnitte vorhandener Run-Artefakte und kann
  dasselbe resident geladene Modell mit einer getrennten Refiner-Rolle nutzen.
  Ein späterer Refiner auf Arc oder über Prime Intellect bleibt durch dieselbe
  Schnittstelle möglich.
- Strukturierte Vorschläge sind in `prompt_overlay`, `memory`, `skills` und
  `subagents` getrennt und müssen Aktionsevidenz, Scope, erwarteten Nutzen und
  Rücknahmebedingung nennen.
- Skills dürfen nur deklarative, allowlistete Intents enthalten; generierter
  Code und Raum-Reset sind ausgeschlossen. Sub-Agent-Spezifikationen bleiben
  read-only und dürfen lediglich Intents empfehlen.
- Ereignisbasierte Trigger laufen nur zwischen abgeschlossenen Aktionen.
  Inaktive Generationen werden versioniert im Run-Verzeichnis gespeichert;
  Modell- oder Validierungsfehler beeinträchtigen den Gameplay-Loop nicht.
- Ein echter, emulatorfreier Shadow-Smoke gegen
  `Qwen3-VL-4B-Spatial-Analysisv8-Q8_0.gguf` auf CUDA bestand Schema und
  Validator. Das Modell erkannte eine A-B-A-B-Navigationsschleife und schlug
  mangels ausreichender Evidenz konservativ keine aktive Änderung vor.
- Ein vollständiger Mesen-Live-Smoke erzeugte aus einer harmlosen, bestätigten
  Blickrichtungsänderung die inaktive Generation
  `harness_shadow_live_smoke_02/live/harness_evolution/generation_0001.json`.
  Der Trigger `model_wait_loop`, Action-Range `[1,1]`, `active: false` und
  `proposed_not_applied` bestätigen den verdrahteten Shadow-Pfad ohne
  Gameplay-Mutation.
- Große `maxLength`-Angaben ließen den llama.cpp-Grammarparser scheitern. Die
  Provider-Grammatik verzichtet nun darauf; die unveränderten Längenlimits
  werden nach der Ausgabe im `HarnessProposalValidator` erzwungen.
- Verifiziert: 230 Tool-/Agent-Tests und 11 WRAM-Discovery-Tests grün.
- Der vollständige runübergreifende Flow ergänzt kanonische Kandidaten,
  Zwei-Run-Promotion, Add/Update/Retire mit gelernter `target_id`, begrenzte
  aktive Canaries, per-Action-Metriken und automatischen Rollback.
- Gated Advice wird als niedriger priorisierter `learned_harness`-Kontext
  eingespeist. Deklarative Skills passieren den echten Intent-Parser;
  Runtime-Subagents nutzen dasselbe residente Modell, ausschließlich read-only
  Werkzeuge und liefern nur normalisierte Empfehlungen.
- Shadow und Gated sind hart getrennt: Shadow sammelt, sieht und attribuiert
  aber keine aktiven Canaries. Isolierte Stores sind über
  `--harness-state-path` möglich.
- Der semantische Validator blockiert ungültige Anwendungs-Scopes,
  Safety-/Thinking-Gate-Umgehung, unsichere Skill-Schritte und duplizierte oder
  nicht allowlistete Subagent-Tools.
- Ein isolierter Gated-Mesen-Live-Smoke bestätigte den gesamten Pfad von echter
  WRAM-Action-Evidenz über Refiner und globalen Kandidatenstore bis zur
  inaktiven Review-Queue; keine Testkandidaten gelangten in den produktiven
  Store.

## 2026-08-09 — Raum-4-Puzzle, Raum-5-Transit und dynamische Gegner

- Qwen löste das Säulenrätsel in Raum 4 live mit der korrigierten Minimalfolge:
  Säule einmal von `[8,21]` nach `[8,20]` nord schieben, Guy über
  `[9,21] -> [9,20]` auf die Ostseite bringen und anschließend west bis zum
  Schalter `[4,20]` schieben. Run 76 ist der erste Live-Nachweis dieser Folge.
- Der Kontext liefert nach dem einmaligen Nord-Push sofort natürlichsprachliches
  Erfolgsfeedback. Eine Wiederholung ist im exakten Folgezustand `not_advised`,
  nicht global verboten. Das lässt dieselbe Aktion für andere Gegner oder
  Rätsel weiterhin zu.
- Das temporäre Puzzle-ASCII wird pro Entscheidung erzeugt und kann Actor,
  bewegliches Objekt, Empfänger, nächste Standposition und temporäre Barrieren
  darstellen. Nach erreichtem Objektziel werden die temporären Barrieren
  entfernt, damit sie den realen Ausgang nicht als Wand maskieren.
- Die gemeinsam per Mesen aufgenommenen Raumgrenzen ersetzen fehlerhafte
  Schätzungen: Raum-4-Ausgangsschwelle `[6,17]`, stabiler Raum-5-Entry `[6,14]`.
  Die gelöste Exitroute benutzt jetzt x=6 statt x=5.
- Raum 5 wurde mit WRAM-Koordinaten und Referenzbildern vermessen:
  - Sprünge `[7,9] -> [8,11]` und `[7,10] -> [8,12]`
  - Leiter `[13,12] <-> [13,10]`
  - Ausgangsschwelle `[16,8]`
- Der U-förmige Transit Raum 5 -> Raum 6 ist als explizite Checkpointfolge
  hinterlegt: `[16,8] -> [16,6] -> [19,6] -> [19,8]`. Er wird nicht mehr als
  eigener nummerierter Raum behandelt.
- `OnlineNavigationMapper.room_for()` priorisiert nun den exakt verifizierten
  ersten Tile eines Nachfolgeraums gegenüber überlappenden Vorgänger-Bounds.
  Ein Regressionstest deckt den überlappenden Raum-5/6-Entry bei `[19,8]` ab.
- Secret-Skills-Cave-spezifische Resetregel dokumentiert: Nach Verlassen eines
  Raums darf nicht resetet werden, wenn der vorherige Raum noch benötigt wird,
  weil eine Rückkehr danach unmöglich ist.
- Für bewegliche Dungeon-Gegner wurde die Datenautorität geklärt: Actor-Slots
  liefern Sprite-ID und exakte X/Y-Position; der Mapbuffer zeigt nur
  entity-agnostische Belegung. Ein Guy-Schritt, Schwertschlag oder Toolzug kann
  einen Monsterzug auslösen, garantiert aber kein X/Y-Delta. Unveränderte
  Position wird daher niemals als Untätigkeit, Wand oder Niederlage gedeutet.
- Referenzaufnahmen wurden unter
  `data/vision_observations/secret_skills_cave_room5*` und
  `data/vision_observations/secret_skills_cave_room6/` abgelegt.
- Verifikation: 110 fokussierte Navigation-/Kontext-/Dungeon-Tests sowie die
  vollständigen 206 Tool-/Agent-Tests und 11 WRAM-Discovery-Tests grün.

## 2026-08-06 — RTX-Spatial-Baseline und schlanker Exploration-Kontext

- Run 41 lieferte den ersten bestaetigten autonomen Qwen-Live-Durchgang durch
  Raum 3; Run 42 reproduzierte dasselbe Ergebnis unabhaengig und endete erneut
  bei `(17,20)` im sichtbaren Zwei-Tueren-Transitraum: Bruecke aktivieren,
  West-Kollision umgehen, Tueranker `(17,23)` erreichen und nach Norden durch
  die Tuer gehen.
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
