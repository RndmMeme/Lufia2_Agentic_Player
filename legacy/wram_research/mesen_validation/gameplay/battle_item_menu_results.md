# Battle-Item-Menü-Audit

Status: **CONFIRMED**

- 96 feste Zweibyte-Slots: `7E:0A8D-0B4C`, Länge `0xC0`.
- Slot 1 leer, Charred newt Slot 2, Curselifter Slot 3.
- Auswahlbyteoffset `7E:0012 = 2*(Slot-1)`.
- Renderattribut `20` nutzbar, `24` deaktiviert.
- Leere Slots bleiben im Menü erhalten; keine Komprimierung.
- Charred newt: Command `03`, Rohpaar `01 02`; Auswahlübergang leerte den Slot kurzzeitig. Erst final leerer Slot plus +5 MP beweist die Ausführung.
