# Battle-Targeting-WRAM-Audit

Status: **CONFIRMED**

- Gespeicherte Zielmaske: `7F:F560 + slot*0x0C + 0x00`.
- Gruppe: `01,02,04,08`; alle vier `0F`.
- Gegner: Flag `80` plus Zielbits; live bestaetigt `81,82,84`, alle drei `87`.
- Gegnerbits `08,10,20` und alle sechs `BF` sind strukturell abgeleitet, noch nicht live beobachtet.
- `7E:0026` ist nur der temporaere nullbasierte Cursorindex und erkennt den R/Alle-Modus nicht.
- `command + 0x0A` ist die Akteurmaske, nicht das Ziel.
