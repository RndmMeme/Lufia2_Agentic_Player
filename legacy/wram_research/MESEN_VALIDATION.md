# Mesen bridge validation

Live geprüft mit Mesen 2.1.1 und:

- ROM: `Lufia_II_-_Rise_of_the_Sinistrals_USA.1721649189.sfc`
- SHA-1: `1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0`
- Mesen-Memory-Type: `snesWorkRam`
- Dumpgröße: 131072 Byte

## Bestätigte Werte

- `7E:30C8`: `53 20 54 20 41 20 52 20 54 20` = sichtbarer Text `START`
- `7E:0108-0109`: Save-Auswahlcursor, Wert plus Beiwert
- Live-Beispiel `88 34`: Screenshot zeigte gleichzeitig Save 2 oben rechts

### Auswahlbildschirm vollständig geprüft

WRAM-Wert und Screenshot wurden jeweils atomar im selben Mesen-End-Frame
erfasst:

| Sichtbare Auswahl | `7E:0108-0109` | Nachweis |
|---|---|---|
| START | `10 14` | [Screenshot](validation/selection_screen/start_10_14.png) |
| RETRY | `50 14` | [Screenshot](validation/selection_screen/retry_50_14.png) |
| GIFT | `90 14` | [Screenshot](validation/selection_screen/gift_90_14.png) |
| SAVE FILE 1 | `10 34` | [Screenshot](validation/selection_screen/save1_10_34.png) |
| SAVE FILE 2 | `88 34` | [Screenshot](validation/selection_screen/save2_88_34.png) |
| SAVE FILE 3 | `10 8C` | [Screenshot](validation/selection_screen/save3_10_8C.png) |
| SAVE FILE 4 | `88 8C` | [Screenshot](validation/selection_screen/save4_88_8C.png) |

Ergebnis: Alle sieben aus Snes9x manuell gepflegten Bytepaare sind in Mesen
inhaltlich korrekt. Widerlegt war nur die frühere Adressumrechnung, nicht die
Wertetabelle.

## Widerlegte Annahme

Die bisherige Dokumentannahme, dass die alte x64-Snes9x-Hostadresse
`0xA30000` direkt `7E:0000` repräsentiert, ist falsch. Große Datenbereiche
zeigen zwar einen häufigen Versatz von `-0x2314`, aber Snes9x-Hostspiegel sind
nicht global linear. Die alten absoluten Prozessadressen dürfen daher nur noch
als Quellenhinweis dienen und müssen einzeln gegen Mesens echtes
`snesWorkRam` validiert werden.
