# Battle-WRAM-Audit

Status: **CONFIRMED**

- Gegner-HP: `7E:162C + slot * 0xBE`, uint16 LE.
- Party-Command: `7F:F560 + slot * 0x0C + 0x04`.
- Attack `01`, Defend `04`.
- Permanenter Charakterblock `+0x13` blieb unverändert und ist widerlegt.
