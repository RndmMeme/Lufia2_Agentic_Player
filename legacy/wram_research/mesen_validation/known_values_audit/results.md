# Live-Audit der vorhandenen WRAM-Angaben

- ROM: `Lufia_II_-_Rise_of_the_Sinistrals_USA.1721649189.sfc`
- SHA-1: `1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0`
- WRAM: `131072` Bytes
- Erkannter Bildschirm: `name`
- Ergebnis: `{'CONFIRMED': 15}`

| Status | Angabe | Adresse | Erwartet | Beobachtet | Beleg |
|---|---|---|---|---|---|
| CONFIRMED | NAME-Überschrift | 7E:314C-7E:3153 | 4E 20 41 20 4D 20 45 20 | 4E 20 41 20 4D 20 45 20 | Legacy-UI-Adresse 0xA35460, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Namensfeld initial | 7E:3162-7E:316B | 30 20 5F 20 5F 20 5F 20 5F 20 | 30 20 5F 20 5F 20 5F 20 5F 20 | Legacy-UI-Adresse 0xA35476, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Ziffern 0-9 | 7E:324C-7E:3273 | 30 20 20 20 31 20 20 20 32 20 20 20 33 20 20 20 34 20 20 20 20 20 35 20 20 20 36 20 20 20 37 20 20 20 38 20 20 20 39 20 | 30 20 20 20 31 20 20 20 32 20 20 20 33 20 20 20 34 20 20 20 20 20 35 20 20 20 36 20 20 20 37 20 20 20 38 20 20 20 39 20 | Legacy-UI-Adresse 0xA35560, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben A-E | 7E:32CC-7E:32DC | 41 20 20 20 42 20 20 20 43 20 20 20 44 20 20 20 45 | 41 20 20 20 42 20 20 20 43 20 20 20 44 20 20 20 45 | Legacy-UI-Adresse 0xA355E0, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben a-e | 7E:32E2-7E:32F2 | 61 20 20 20 62 20 20 20 63 20 20 20 64 20 20 20 65 | 61 20 20 20 62 20 20 20 63 20 20 20 64 20 20 20 65 | Legacy-UI-Adresse 0xA355F6, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben F-J | 7E:334C-7E:335C | 46 20 20 20 47 20 20 20 48 20 20 20 49 20 20 20 4A | 46 20 20 20 47 20 20 20 48 20 20 20 49 20 20 20 4A | Legacy-UI-Adresse 0xA35660, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben f-j | 7E:3362-7E:3372 | 66 20 20 20 67 20 20 20 68 20 20 20 69 20 20 20 6A | 66 20 20 20 67 20 20 20 68 20 20 20 69 20 20 20 6A | Legacy-UI-Adresse 0xA35676, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben K-O | 7E:33CC-7E:33DC | 4B 20 20 20 4C 20 20 20 4D 20 20 20 4E 20 20 20 4F | 4B 20 20 20 4C 20 20 20 4D 20 20 20 4E 20 20 20 4F | Legacy-UI-Adresse 0xA356E0, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben k-o | 7E:33E2-7E:33F2 | 6B 20 20 20 6C 20 20 20 6D 20 20 20 6E 20 20 20 6F | 6B 20 20 20 6C 20 20 20 6D 20 20 20 6E 20 20 20 6F | Legacy-UI-Adresse 0xA356F6, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben P-T | 7E:344C-7E:345C | 50 20 20 20 51 20 20 20 52 20 20 20 53 20 20 20 54 | 50 20 20 20 51 20 20 20 52 20 20 20 53 20 20 20 54 | Legacy-UI-Adresse 0xA35760, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben p-t | 7E:3462-7E:3472 | 70 20 20 20 71 20 20 20 72 20 20 20 73 20 20 20 74 | 70 20 20 20 71 20 20 20 72 20 20 20 73 20 20 20 74 | Legacy-UI-Adresse 0xA35776, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben U-Y | 7E:34CC-7E:34DC | 55 20 20 20 56 20 20 20 57 20 20 20 58 20 20 20 59 | 55 20 20 20 56 20 20 20 57 20 20 20 58 20 20 20 59 | Legacy-UI-Adresse 0xA357E0, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben u-y | 7E:34E2-7E:34F2 | 75 20 20 20 76 20 20 20 77 20 20 20 78 20 20 20 79 | 75 20 20 20 76 20 20 20 77 20 20 20 78 20 20 20 79 | Legacy-UI-Adresse 0xA357F6, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Großbuchstaben Z ! ? | 7E:354C-7E:3554 | 5A 20 20 20 21 20 20 20 3F | 5A 20 20 20 21 20 20 20 3F | Legacy-UI-Adresse 0xA35860, lokal bestätigter UI-Versatz -0x2314 |
| CONFIRMED | Kleinbuchstaben z ! ? | 7E:3562-7E:356A | 7A 20 20 20 21 20 20 20 3F | 7A 20 20 20 21 20 20 20 3F | Legacy-UI-Adresse 0xA35876, lokal bestätigter UI-Versatz -0x2314 |
