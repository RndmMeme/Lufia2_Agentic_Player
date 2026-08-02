# Battle-IP-Menü-Audit

Status: **CONFIRMED**

- Cursorindex: `7E:0014`, Werte `00` bis `05`.
- Cursor-Y: `7E:0101`, `20 + Zeile * 0x0C`.
- Equipment-Arbeitsliste: `7E:1357-1362`, sechs Item-IDs.
- Renderzeilen: `7E:3147 + Zeile * 0x80`.
- IP-Name innerhalb einer Zeile: `+0x1B`.
- Nutzbarkeitsattribut bei `Zeile + 0x02`: `20` ausführbar, `24` zu wenig IP.
- Regel bestätigt: `aktuelle IP >= Kosten`; Guy hatte `96` IP.
- Sleep stinger: Auswahl/Ziel hielten IP bei `96`; erst die Ausführung senkte `7E:0DE5` auf `0`.
- Keine separate Sechserliste aus IP-Fähigkeits-IDs beobachtet.
