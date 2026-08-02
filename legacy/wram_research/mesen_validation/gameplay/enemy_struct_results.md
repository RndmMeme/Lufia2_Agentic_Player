# Enemy-Struct-WRAM-Audit

Status: **CONFIRMED**

- Vollstaendiger Struct: `7E:1618 + slot*0xBE`.
- Der alte Anker `7E:162C` ist `CurrentHP` bei Struct `+0x14`.
- Status liegt bei `+0x12`; Tod setzte live Bit `04`.
- Freeze ball setzte am unbeschaedigten Ziel live Paralyze-Bit `08`.
- Current/Max HP und MP sowie ATP, DFP, STR, AGL, INT, GUT und MGR folgen den Charakteroffsets.
- Weitere Statusbits benoetigen kontrollierte Gift/Schlaf/Paralyse-Tests.
