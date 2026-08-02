# WRAM-Mapping als Kampagne

Ziel ist nicht, jede denkbare Spielsituation einzeln zu katalogisieren. Das
wäre kombinatorisch praktisch unbegrenzt. Gemappt werden die beobachtbaren
Zustände, die der AI-Player für Entscheidungen benötigt. Ähnliche Aktionen
werden als Kampagne aufgenommen und anschließend gemeinsam ausgewertet.

## Grundregeln

- Pro Session nur eine kontrollierte Variable verändern.
- Fünf Wiederholungen aus demselben Save-State oder derselben reproduzierbaren
  Ausgangslage aufnehmen.
- Ähnliche Situationen getrennt aufnehmen; nicht mehrere Aktionen in einen
  einzelnen Trial packen.
- Generische Zustände über die Schnittmenge mehrerer Situationen suchen.
- Einen Kandidaten erst als bestätigt markieren, wenn ein Gegenversuch die
  erwartete Umkehrung oder Abwesenheit zeigt.

## Empfohlene Reihenfolge

### 1. Kernmodus und Eingabesperren

Jeweils als Lifecycle:

- Textbox geschlossen/offen
- Hauptmenü geschlossen/offen
- Kampf inaktiv/aktiv
- Kartenwechsel inaktiv/aktiv
- Spielereingabe frei/gesperrt

Diese Werte segmentieren alle späteren Aufnahmen und haben daher höchste
Priorität.

### 2. Bewegung

Normale Sessions mit eindeutigen Namen:

- `laufen runter`
- `laufen hoch`
- `laufen rechts`
- `laufen links`
- `stehen bleiben`

Danach jeweils Gegenrichtungen vergleichen. Ein echter Y-Wert steigt bei
`runter`, fällt bei `hoch` und sollte bei reiner Horizontalbewegung stabil
bleiben. Für X gilt das entsprechend.

### 3. Textboxfamilie

Jeweils als eigener Lifecycle:

- NPC ansprechen
- Schild lesen
- Truhe mit Textmeldung
- Item-erhalten-Meldung
- Save-/Priesterdialog

Danach die Sessions mit `compare` schneiden. Gemeinsame reversible Kandidaten
sind wahrscheinliche generische Textboxzustände. Nur in einer Session
auftauchende Kandidaten sind eher Textinhalt, Scriptstatus oder Renderdaten.

### 4. A-Interaktionen

Aus identischer Position und Blickrichtung getrennt aufnehmen:

- A vor NPC
- A vor Schild
- A vor Tür
- A vor Truhe
- A vor leerer Wand

Die leere Wand ist die Scheinaktion. Werte, die auch dort wechseln, gehören
eher zur Eingabe als zum Interaktionsziel. Anschließend die entstandenen
Textboxen oder Menüs mit dem Lifecycle-Profil untersuchen.

### 5. Auswahl und Menücursor

Alternierend aufnehmen:

- Auswahl A -> B
- Auswahl B -> A
- eine zweite Zeile oder Spalte
- oberer/unterer Rand mit blockierter Bewegung

Dadurch lassen sich Cursorwert, Zeile, Spalte, Scrollposition und bloße
Darstellungsdaten trennen.

### 6. Ressourcen und Zähler

Mit bekanntem Delta aufnehmen:

- HP/MP verlieren und heilen
- Gold erhalten und ausgeben
- Itemmenge +1/-1
- Erfahrung erhalten
- Levelanstieg

Hier ist `--expected-delta` sinnvoller als ein allgemeiner Diff.

### 7. Strukturen und Listen

Mehrere unterschiedliche Slots gezielt verändern:

- Partyaufstellung
- Inventarslots
- Ausrüstung
- Zauberlisten
- aktive NPC-/Objektslots

Nicht nur einen Slot testen. Wiederkehrende Abstände zwischen geänderten
Adressen verraten Stride, Feldbreite und Strukturgrenzen.

## Bestätigungsstandard

Eine Adresse gilt erst dann als belastbar, wenn:

1. sie in mindestens vier von fünf Wiederholungen zum Zielverhalten passt,
2. die passende Gegenprobe das inverse oder stabile Verhalten zeigt,
3. sie nicht nur einen konkreten Text-/Tileinhalt abbildet,
4. Datenbreite und Endianness geklärt sind,
5. sie in mindestens einer zweiten Spielsituation derselben Semantik
   funktioniert.
