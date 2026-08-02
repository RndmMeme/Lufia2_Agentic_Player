# Shop-WRAM-Audit

Status: **CONFIRMED**

| Capture | Name @ 7E:0B77 | Preis @ 7E:0B89 | Cursor @ 7E:1574 | Ergebnis |
|---|---|---:|---:|---|
| shop_item_active_1.bin | Hi-Potion | 95 | 0x0000 | PASS |
| shop_item_active_2.bin | Confuse ball | 79 | 0x000C | PASS |
| shop_item_active_3.bin | Escape | 95 | 0x0018 | PASS |

`0x2CCE` blieb in allen drei Zuständen unverändert und ist als ausgewählter Shoppreis für echtes Mesen-WRAM widerlegt.
