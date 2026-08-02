# Battle-Magic-Menü-Audit

Status: **CONFIRMED**

- 36 feste Spellslots bei Guy: `7E:0DBF-0DE2`.
- Fensterstart `7E:0011`, absoluter Cursorindex `7E:0012`.
- Spalte `7E:0013`, sichtbare Zeile `7E:0014`.
- Renderzeilen ab `7E:3146`, Stride `0x80`, rechte Spalte `+0x1C`.
- Renderattribut `20` ausführbar, `24` deaktiviert.
- Livekosten stammen aus der randomisierten ROM und weichen von Vanilla-Daten ab.
- Leere `FF`-Slots sind navigierbar; Bestätigen wird ignoriert.
- Fireball speicherte Spell-ID `04`; MP sanken erst bei Ausführung von `471` auf `465`.
