# Lufia II WRAM base of truth

ROM SHA-1: `1D0A95DDCCEB399E8FEC51BA5CBB6A6C5D30E0E0`  
Live backend: `Mesen 2.1.1 / snesWorkRam / 128 KiB`

Diese Datei trennt echte Mesen-WRAM-Adressen von historischen Snes9x-Prozess- und Hostspiegel-Adressen. Ein mechanisch abgeleiteter Kandidat ist keine Bestätigung.

## Status

- `candidate`: 11
- `confirmed`: 59
- `confirmed_structure`: 217
- `observed`: 25
- `partially_confirmed`: 1
- `unreliable`: 1

## Semantische Adressen

| Status | Feld | Legacy | Mesen | Begründung |
|---|---|---|---|---|
| confirmed | Gold | 0x02D9E | 7E:0A8A | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | PartySlots | 0x02D8F, 0x02D90, 0x02D91, 0x02D92 | 7E:0A7B, 7E:0A7C, 7E:0A7D, 7E:0A7E | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | CapsuleSlots | 0x034CF, 0x034D0, 0x034D1, 0x034D2, 0x034D3, 0x034D4, 0x034D5 | 7E:11BB, 7E:11BC, 7E:11BD, 7E:11BE, 7E:11BF, 7E:11C0, 7E:11C1 | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | InventoryStart | 0x02DA1 | 7E:0A8D | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | InventoryEnd | 0x02E60 | 7E:0B4C | Controlled Mesen transition and/or exact visible UI value. |
| observed | EventFlagsStart | 0x0077E | 7E:077E | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EventFlagsEnd | 0x0079D | 7E:079D | Source field was added from direct Mesen/UI-buffer observation. |
| observed | ScenarioStart | 0x02C32 | 7E:091E | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ScenarioEnd | 0x02C34 | 7E:0920 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | DungeonFlagStart | 0x02A96 | 7E:0782 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | DungeonFlagEnd | 0x02A9F | 7E:078B | Corrected block location is plausible; semantic state transition remains pending. |
| observed | TransportFlag | 0x02CF5 | 7E:09E1 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ShipXFast | 0x0379C | 7E:1488 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ShipXSlow | 0x0379D | 7E:1489 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ShipYFast | 0x0379F | 7E:148B | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ShipYSlow | 0x037A0 | 7E:148C | Corrected block location is plausible; semantic state transition remains pending. |
| observed | WalkXFast | 0x0377F | 7E:146B | Corrected block location is plausible; semantic state transition remains pending. |
| observed | WalkXSlow | 0x03780 | 7E:146C | Corrected block location is plausible; semantic state transition remains pending. |
| observed | WalkYFast | 0x03782 | 7E:146E | Corrected block location is plausible; semantic state transition remains pending. |
| observed | WalkYSlow | 0x03783 | 7E:146F | Corrected block location is plausible; semantic state transition remains pending. |
| confirmed | CurrentMap | 0x028C0 | 7E:05AC | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | DungeonXHigh | 0x03532 | 7E:121E | Controlled Mesen transition and/or exact visible UI value. |
| candidate | DungeonXLow | 0x03534 | 7E:1220 | Mechanical family translation only; not promoted without semantic evidence. |
| confirmed | DungeonYHigh | 0x0353A | 7E:1226 | Controlled Mesen transition and/or exact visible UI value. |
| candidate | DungeonYLow | 0x0353C | 7E:1228 | Mechanical family translation only; not promoted without semantic evidence. |
| unreliable | DungeonBlocking | 0x03586 | 7E:1272 | Existing candidate contradicted live behavior or documented value domain. |
| observed | MapContextFlag | 0x02CBB | 7E:09A7 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | ExplorationModeFlag | 0x02CBD | 7E:09A9 | Corrected block location is plausible; semantic state transition remains pending. |
| observed | BattleModeFlag | 0x02CBE | 7E:09AA | Corrected block location is plausible; semantic state transition remains pending. |
| confirmed | FacingDirectionStateMirror | 0x02CB5 | 7E:09A1 | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | DungeonAxisMirrorX | 0x02368 | 7E:0054 | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | DungeonAxisMirrorY | 0x0236E | 7E:005A | Controlled Mesen transition and/or exact visible UI value. |
| candidate | DungeonAxisChunkY | 0x0236F | 7E:005B | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | ChunkBorderVHigh | 0x0353B | 7E:1227 | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | ChunkBorderVLow | 0x0353D | 7E:1229 | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | ChunkBorderHHigh | 0x03533 | 7E:121F | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | ChunkBorderHLow | 0x03535 | 7E:1221 | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | DungeonSpawnXHigh | 0x0356F | 7E:125B | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | DungeonSpawnYHigh | 0x03571 | 7E:125D | Mechanical family translation only; not promoted without semantic evidence. |
| confirmed | TownX | 0x028A8 | 7E:0594 | Controlled Mesen transition and/or exact visible UI value. |
| confirmed | TownY | 0x028AA | 7E:0596 | Controlled Mesen transition and/or exact visible UI value. |
| candidate | TownVerticalChunk | 0x028A9 | 7E:0595 | Mechanical family translation only; not promoted without semantic evidence. |
| candidate | TownHorizontalChunk | 0x028AB | 7E:0597 | Mechanical family translation only; not promoted without semantic evidence. |
| confirmed | CurrentToolName | 0x02E8B | 7E:0B77 | Controlled Mesen transition and/or exact visible UI value. |
| observed | EquipmentInspectNameBuffer | 0x0631A | 7E:631A | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentInspectDescriptionStart | 0x05898 | 7E:5898 | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentInspectDescriptionEnd | 0x0597D | 7E:597D | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentInspectMetaStart | 0x042DD | 7E:42DD | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentInspectMetaEnd | 0x04304 | 7E:4304 | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentReplaceListStart | 0x057DD | 7E:57DD | Source field was added from direct Mesen/UI-buffer observation. |
| observed | EquipmentReplaceListEnd | 0x059FD | 7E:59FD | Source field was added from direct Mesen/UI-buffer observation. |
| confirmed | EquipmentRenderPaneStart | 0x053DE | 7E:30CA | Live IP menu render buffer; prompt and all six rows were decoded from Mesen WRAM. |
| confirmed | EquipmentRenderPaneEnd | 0x0575B | 7E:3447 | Corrected live end includes the sixth equipment/IP row, which the legacy boundary omitted. |
| confirmed | EquipmentPromptPaneStart | 0x0535A | 7E:3046 | Interleaved ASCII decoded to the visible text 'Please choose equipment.'. |
| confirmed | EquipmentFirstEntryStart | 0x0545B | 7E:3147 | First live equipment row buffer; visible text starts at the following byte. |
| confirmed | BattleResultExpTextStart | 0x0541C | 7E:1605 | Visible EXP 2689 matched uint16; this is numeric reward data, not text. |
| confirmed | BattleResultGoldTextStart | 0x05744 | 7E:1608 | Visible gold 4140 matched uint16; this is numeric reward data, not text. |
| confirmed | SelectedItemPrice | 0x02CCE | 7E:0B89 | Three visible Dankirk shop rows matched atomically; this field does not follow the general legacy helper delta. |
| confirmed | ShopCursorPosition | 0x03888 | 7E:1574 | Three visible Dankirk shop rows matched atomically; this field does not follow the general legacy helper delta. |
| confirmed_structure | Character.Maxim.base | 0x02EBE | 7E:0BAA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Level | 0x02ECF | 7E:0BBB | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Status | 0x02ED0 | 7E:0BBC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.DefendFlag | 0x02ED1 | 7E:0BBD | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.CurrentHP | 0x02ED2 | 7E:0BBE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.CurrentMP | 0x02ED4 | 7E:0BC0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.MaxHP | 0x02EE6 | 7E:0BD2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.MaxMP | 0x02EE8 | 7E:0BD4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Weapon | 0x02F27 | 7E:0C13 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Armor | 0x02F29 | 7E:0C15 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Hands | 0x02F2B | 7E:0C17 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Headwear | 0x02F2D | 7E:0C19 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Accessories | 0x02F2F | 7E:0C1B | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.Jewels | 0x02F31 | 7E:0C1D | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.ATP | 0x02EEA | 7E:0BD6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.DFP | 0x02EEC | 7E:0BD8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.STR | 0x02EEE | 7E:0BDA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.AGL | 0x02EF0 | 7E:0BDC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.INT | 0x02EF2 | 7E:0BDE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.GUT | 0x02EF4 | 7E:0BE0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.MGR | 0x02EF6 | 7E:0BE2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.ATP_Compare | 0x02EF8 | 7E:0BE4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.DFP_Compare | 0x02EFA | 7E:0BE6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.STR_Compare | 0x02EFC | 7E:0BE8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.AGL_Compare | 0x02EFE | 7E:0BEA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.INT_Compare | 0x02F00 | 7E:0BEC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.GUT_Compare | 0x02F02 | 7E:0BEE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.MGR_Compare | 0x02F04 | 7E:0BF0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.SpellsStart | 0x02F57 | 7E:0C43 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.SpellsEnd | 0x02F7A | 7E:0C66 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Maxim.IP | 0x02F7D | 7E:0C69 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.base | 0x02F7C | 7E:0C68 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Level | 0x02F8D | 7E:0C79 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Status | 0x02F8E | 7E:0C7A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.DefendFlag | 0x02F8F | 7E:0C7B | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.CurrentHP | 0x02F90 | 7E:0C7C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.CurrentMP | 0x02F92 | 7E:0C7E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.MaxHP | 0x02FA4 | 7E:0C90 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.MaxMP | 0x02FA6 | 7E:0C92 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Weapon | 0x02FE5 | 7E:0CD1 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Armor | 0x02FE7 | 7E:0CD3 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Hands | 0x02FE9 | 7E:0CD5 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Headwear | 0x02FEB | 7E:0CD7 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Accessories | 0x02FED | 7E:0CD9 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.Jewels | 0x02FEF | 7E:0CDB | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.ATP | 0x02FA8 | 7E:0C94 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.DFP | 0x02FAA | 7E:0C96 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.STR | 0x02FAC | 7E:0C98 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.AGL | 0x02FAE | 7E:0C9A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.INT | 0x02FB0 | 7E:0C9C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.GUT | 0x02FB2 | 7E:0C9E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.MGR | 0x02FB4 | 7E:0CA0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.ATP_Compare | 0x02FB6 | 7E:0CA2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.DFP_Compare | 0x02FB8 | 7E:0CA4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.STR_Compare | 0x02FBA | 7E:0CA6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.AGL_Compare | 0x02FBC | 7E:0CA8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.INT_Compare | 0x02FBE | 7E:0CAA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.GUT_Compare | 0x02FC0 | 7E:0CAC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.MGR_Compare | 0x02FC2 | 7E:0CAE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.SpellsStart | 0x03015 | 7E:0D01 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.SpellsEnd | 0x03038 | 7E:0D24 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Selan.IP | 0x0303B | 7E:0D27 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.base | 0x0303A | 7E:0D26 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Level | 0x0304B | 7E:0D37 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Status | 0x0304C | 7E:0D38 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.DefendFlag | 0x0304D | 7E:0D39 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.CurrentHP | 0x0304E | 7E:0D3A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.CurrentMP | 0x03050 | 7E:0D3C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.MaxHP | 0x03062 | 7E:0D4E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.MaxMP | 0x03064 | 7E:0D50 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Weapon | 0x030A3 | 7E:0D8F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Armor | 0x030A5 | 7E:0D91 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Hands | 0x030A7 | 7E:0D93 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Headwear | 0x030A9 | 7E:0D95 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Accessories | 0x030AB | 7E:0D97 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.Jewels | 0x030AD | 7E:0D99 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.ATP | 0x03066 | 7E:0D52 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.DFP | 0x03068 | 7E:0D54 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.STR | 0x0306A | 7E:0D56 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.AGL | 0x0306C | 7E:0D58 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.INT | 0x0306E | 7E:0D5A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.GUT | 0x03070 | 7E:0D5C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.MGR | 0x03072 | 7E:0D5E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.ATP_Compare | 0x03074 | 7E:0D60 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.DFP_Compare | 0x03076 | 7E:0D62 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.STR_Compare | 0x03078 | 7E:0D64 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.AGL_Compare | 0x0307A | 7E:0D66 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.INT_Compare | 0x0307C | 7E:0D68 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.GUT_Compare | 0x0307E | 7E:0D6A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.MGR_Compare | 0x03080 | 7E:0D6C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.SpellsStart | 0x030D3 | 7E:0DBF | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.SpellsEnd | 0x030F6 | 7E:0DE2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Guy.IP | 0x030F9 | 7E:0DE5 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.base | 0x030F8 | 7E:0DE4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Level | 0x03109 | 7E:0DF5 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Status | 0x0310A | 7E:0DF6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.DefendFlag | 0x0310B | 7E:0DF7 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.CurrentHP | 0x0310C | 7E:0DF8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.CurrentMP | 0x0310E | 7E:0DFA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.MaxHP | 0x03120 | 7E:0E0C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.MaxMP | 0x03122 | 7E:0E0E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Weapon | 0x03161 | 7E:0E4D | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Armor | 0x03163 | 7E:0E4F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Hands | 0x03165 | 7E:0E51 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Headwear | 0x03167 | 7E:0E53 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Accessories | 0x03169 | 7E:0E55 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.Jewels | 0x0316B | 7E:0E57 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.ATP | 0x03124 | 7E:0E10 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.DFP | 0x03126 | 7E:0E12 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.STR | 0x03128 | 7E:0E14 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.AGL | 0x0312A | 7E:0E16 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.INT | 0x0312C | 7E:0E18 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.GUT | 0x0312E | 7E:0E1A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.MGR | 0x03130 | 7E:0E1C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.ATP_Compare | 0x03132 | 7E:0E1E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.DFP_Compare | 0x03134 | 7E:0E20 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.STR_Compare | 0x03136 | 7E:0E22 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.AGL_Compare | 0x03138 | 7E:0E24 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.INT_Compare | 0x0313A | 7E:0E26 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.GUT_Compare | 0x0313C | 7E:0E28 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.MGR_Compare | 0x0313E | 7E:0E2A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.SpellsStart | 0x03191 | 7E:0E7D | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.SpellsEnd | 0x031B4 | 7E:0EA0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Artea.IP | 0x031B7 | 7E:0EA3 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.base | 0x031B6 | 7E:0EA2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Level | 0x031C7 | 7E:0EB3 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Status | 0x031C8 | 7E:0EB4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.DefendFlag | 0x031C9 | 7E:0EB5 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.CurrentHP | 0x031CA | 7E:0EB6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.CurrentMP | 0x031CC | 7E:0EB8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.MaxHP | 0x031DE | 7E:0ECA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.MaxMP | 0x031E0 | 7E:0ECC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Weapon | 0x0321F | 7E:0F0B | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Armor | 0x03221 | 7E:0F0D | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Hands | 0x03223 | 7E:0F0F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Headwear | 0x03225 | 7E:0F11 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Accessories | 0x03227 | 7E:0F13 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.Jewels | 0x03229 | 7E:0F15 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.ATP | 0x031E2 | 7E:0ECE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.DFP | 0x031E4 | 7E:0ED0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.STR | 0x031E6 | 7E:0ED2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.AGL | 0x031E8 | 7E:0ED4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.INT | 0x031EA | 7E:0ED6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.GUT | 0x031EC | 7E:0ED8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.MGR | 0x031EE | 7E:0EDA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.ATP_Compare | 0x031F0 | 7E:0EDC | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.DFP_Compare | 0x031F2 | 7E:0EDE | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.STR_Compare | 0x031F4 | 7E:0EE0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.AGL_Compare | 0x031F6 | 7E:0EE2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.INT_Compare | 0x031F8 | 7E:0EE4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.GUT_Compare | 0x031FA | 7E:0EE6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.MGR_Compare | 0x031FC | 7E:0EE8 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.SpellsStart | 0x0324F | 7E:0F3B | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.SpellsEnd | 0x03272 | 7E:0F5E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Tia.IP | 0x03275 | 7E:0F61 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.base | 0x03274 | 7E:0F60 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Level | 0x03285 | 7E:0F71 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Status | 0x03286 | 7E:0F72 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.DefendFlag | 0x03287 | 7E:0F73 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.CurrentHP | 0x03288 | 7E:0F74 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.CurrentMP | 0x0328A | 7E:0F76 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.MaxHP | 0x0329C | 7E:0F88 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.MaxMP | 0x0329E | 7E:0F8A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Weapon | 0x032DD | 7E:0FC9 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Armor | 0x032DF | 7E:0FCB | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Hands | 0x032E1 | 7E:0FCD | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Headwear | 0x032E3 | 7E:0FCF | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Accessories | 0x032E5 | 7E:0FD1 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.Jewels | 0x032E7 | 7E:0FD3 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.ATP | 0x032A0 | 7E:0F8C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.DFP | 0x032A2 | 7E:0F8E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.STR | 0x032A4 | 7E:0F90 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.AGL | 0x032A6 | 7E:0F92 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.INT | 0x032A8 | 7E:0F94 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.GUT | 0x032AA | 7E:0F96 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.MGR | 0x032AC | 7E:0F98 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.ATP_Compare | 0x032AE | 7E:0F9A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.DFP_Compare | 0x032B0 | 7E:0F9C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.STR_Compare | 0x032B2 | 7E:0F9E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.AGL_Compare | 0x032B4 | 7E:0FA0 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.INT_Compare | 0x032B6 | 7E:0FA2 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.GUT_Compare | 0x032B8 | 7E:0FA4 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.MGR_Compare | 0x032BA | 7E:0FA6 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.SpellsStart | 0x0330D | 7E:0FF9 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.SpellsEnd | 0x03330 | 7E:101C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Dekar.IP | 0x03333 | 7E:101F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.base | 0x03332 | 7E:101E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Level | 0x03343 | 7E:102F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Status | 0x03344 | 7E:1030 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.DefendFlag | 0x03345 | 7E:1031 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.CurrentHP | 0x03346 | 7E:1032 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.CurrentMP | 0x03348 | 7E:1034 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.MaxHP | 0x0335A | 7E:1046 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.MaxMP | 0x0335C | 7E:1048 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Weapon | 0x0339B | 7E:1087 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Armor | 0x0339D | 7E:1089 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Hands | 0x0339F | 7E:108B | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Headwear | 0x033A1 | 7E:108D | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Accessories | 0x033A3 | 7E:108F | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.Jewels | 0x033A5 | 7E:1091 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.ATP | 0x0335E | 7E:104A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.DFP | 0x03360 | 7E:104C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.STR | 0x03362 | 7E:104E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.AGL | 0x03364 | 7E:1050 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.INT | 0x03366 | 7E:1052 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.GUT | 0x03368 | 7E:1054 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.MGR | 0x0336A | 7E:1056 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.ATP_Compare | 0x0336C | 7E:1058 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.DFP_Compare | 0x0336E | 7E:105A | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.STR_Compare | 0x03370 | 7E:105C | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.AGL_Compare | 0x03372 | 7E:105E | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.INT_Compare | 0x03374 | 7E:1060 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.GUT_Compare | 0x03376 | 7E:1062 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.MGR_Compare | 0x03378 | 7E:1064 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.SpellsStart | 0x033CB | 7E:10B7 | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.SpellsEnd | 0x033EE | 7E:10DA | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed_structure | Character.Lexis.IP | 0x033F1 | 7E:10DD | 0xBE stride and corrected block layout confirmed. Active party values were checked against visible status screens; inactive blocks have name anchors. |
| confirmed | Enemy.Enemy_1.currentHpAnchor | 0x03940 | 7E:162C | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | Enemy.Enemy_2.currentHpAnchor | 0x039FE | 7E:16EA | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | Enemy.Enemy_3.currentHpAnchor | 0x03ABC | 7E:17A8 | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | Enemy.Enemy_4.currentHpAnchor | 0x03B7A | 7E:1866 | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | Enemy.Enemy_5.currentHpAnchor | 0x03C38 | 7E:1924 | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | Enemy.Enemy_6.currentHpAnchor | 0x03CF6 | 7E:19E2 | This legacy-derived address is CurrentHP, not the full struct base. Six-slot 0xBE layout confirmed; three Garbost had 637 HP. |
| confirmed | PreviousMap |  | 7E:05AE | uint8 origin map: Overworld held 05 after leaving Secret Skills Cave; the cave held 00 after entry from Overworld. |
| confirmed | EnemyCombatStatStruct | Old enemy anchors were CurrentHP, not struct bases | 7E:1618 + slot*0xBE | Three identical Garbost blocks matched the character combat-stat layout exactly. All three had level 50; CurrentHP changed 637->0/336 while MaxHP stayed 637; the defeated slot's status changed 00->04. Freeze ball changed an undamaged target's status 00->08, confirming Paralyze. A second species exposed the inline name Ramia and different stats at the same offsets. Live IDs 54 Garbost and 3B Ramia matched Abyssonym's complete monster table exactly. |
| confirmed | BattlePartyCommandSlots | Character base + 0x13 (contradicted) | 7F:F564, 7F:F570, 7F:F57C, 7F:F588 | Mirrored Attack/Defend tests proved 01/04 and 0x0C slot stride. |
| confirmed | BattlePartyStoredTargetMask |  | 7F:F560, 7F:F56C, 7F:F578, 7F:F584 | Party targets stored 01/02/04/08 and all four 0F. Enemy targets set flag 80: live single targets 81/82/84 and all three 87. Enemy bits 08/10/20 and all-six BF are structurally derived, not yet observed in a rare six-enemy encounter. |
| confirmed | BattleActiveTargetIndex |  | 7E:0026 | Manual left/middle/right selection produced zero-based 00/01/02. This is the fixed temporary cursor only and cannot distinguish R/all-target mode; read the stored command mask after confirmation. |
| confirmed | BattlePartyActorMask |  | 7F:F56A, 7F:F576, 7F:F582, 7F:F58E | The value stayed 04 for Arty while targets changed from 82 to 84; it is an actor mask, not the target or target companion. |
| confirmed | BattleInitiativeQueue |  | 7E:1B8C | Eight materialized entries executed in exact descending order: 266,187,140,133,108,45,45,43. Maximum actor capacity is 11 (four humans, capsule and six enemies). |
| confirmed | BattleActiveAction |  | 7F:F44E | The active actor sequence matched the initiative queue exactly. Ramia targets 08/10/08 identified Tia/capsule/Tia; Tia HP fell 619->596->571 on the two target-08 actions. The randomized ROM action-name pointer table maps hex ID 16 to Tail attack (15=Miracle voice, 17=Picking). |
| confirmed | BattleGroupMenuSelection |  | 7E:0B4E | Held cursor states matched Fight 09, Trade 0A and Escape 0B. The idle value remained 13 across a live B transition from the action cross, so this is not an idle pre-menu detector. |
| confirmed | BattleActionCrossControls | No cursor exists | Stateful UI transition, not a standalone WRAM cursor | From the neutral character action cross: A=Attack, Up+A=Magic, Down+A=IP, Left+A=Item, Right+A=Defend. B returns to the pre-menu containing Fight, Trade Places and Escape. Once a list or target selector is open, navigation and A are simple pulses; R is pressed once to toggle all targets. |
| confirmed | BattleFormation |  | 7E:153D, 7E:153E, 7E:153F, 7E:1540 | Guy/Arty trade changed 02 03 01 04 to 03 02 01 04 without changing canonical party. |
| confirmed | BattleRewardValidity | 0x0541C, 0x05744 | 7E:1605, 7E:1608 | EXP 2689 and gold 4140 matched; old text buffers were unchanged and rewards remain stale after return. |
| confirmed | BattleIpMenuCursor |  | 7E:0014, 7E:0101 | Six manually positioned rows produced index 00-05 and Y values 20,2C,38,44,50,5C. |
| confirmed | BattleIpEquipmentList |  | 7E:1357-1362 | The battle menu copied all six equipped item IDs here in equipment-slot order. |
| confirmed | BattleIpRenderedRows | 0x0545B first row; old end 0x056CE omitted row six | 7E:3147 + row*0x80 | Six screenshots matched six interleaved-ASCII rows. WRAM stores item IDs and rendered names, not a separate six-entry IP-ID list. |
| confirmed | BattleIpAvailability |  | 7E:3149 + row*0x80 | Attribute 20 marked costs <= Guy's 96 IP usable; 24 marked costs above 96 unusable. Equality at 96 was usable. |
| confirmed | BattleIpConsumption |  | 7E:0DE5 | Sleep Stinger cost 96: selection and target confirmation kept 96; actual execution changed 96 to 0. |
| confirmed | BattleMagicMenuCursor |  | 7E:0011-0014, 7E:0100-0101 | True top, horizontal, vertical, first empty and true 36-slot end states matched. |
| confirmed | BattleMagicRenderedRows |  | 7E:3146 + row*0x80 | Two-column scrolling pane exposes randomized live costs and attribute 20 usable / 24 disabled. |
| confirmed | CharacterSpellSlots | Character base + 0x99 | Guy example 7E:0DBF-0DE2 | Battle and field menu share the same fixed 36-slot order; FF slots are empty but navigable. |
| confirmed | BattleMagicSelectionAndConsumption |  | 7F:F564, 7F:F566, Guy 7E:0D3C-0D3D | Fireball produced command 02, spell ID 04; MP stayed 471 through selection then fell to 465 on execution, matching live cost 6. |
| confirmed | BattleItemMenuCursor |  | 7E:0011-0014, 7E:0100-0101 | Empty slot 1, occupied slots 2/3 and true slot 96 end matched fixed raw inventory positions. |
| confirmed | BattleItemRenderedRows |  | 7E:3147 + row*0x80 | Rows preserve empty inventory slots; attribute 20 means battle-usable and 24 means visible but disabled. |
| confirmed | InventorySlotStructure | 0x02DA1-0x02E60 inclusive | 7E:0A8D-0B4C | 96 fixed two-byte slots require 0xC0 bytes; old helper length 0xBF omitted slot 96's second byte. |
| confirmed | BattleItemSelectionAndConsumption |  | 7F:F564, 7F:F566-F567, Charred example 7E:0A8F-0A90 | Charred Newt command 03 stored 01 02. Selection transition temporarily cleared the slot; final empty slot plus Guy MP 465 to 470 proved execution. |
| confirmed | DungeonActorLayout |  | 7E:05D2 + slot, 7E:066A + slot, 7E:0692 + slot, 7E:06BA + slot, 7E:06E2 + slot, 7E:070A + slot, 7F:E466 + slot | Forty slots 00-27; FF is empty. Controlled up/down/left/right changed only the matching tile axis. Movement-state bit 0 distinguishes moving from idle. Stable direction uses 00 south, 02 west, 04 north, 06 east; facing uses low bits 0-3. |
| confirmed | DungeonActorMovementMode |  | 7E:070A + slot | For overworld sprites 80-EF, the runtime byte equals ROM MonsterMoveObject[SpriteID-80]. All six loaded monster actors matched the randomized ROM table. |
| confirmed | DungeonBlockedAttempt | 0x03586 old unsupported claim | 7E:1272, 7E:06BA/06E2 + slot | A visible south-wall attempt produced FF->01 at 7E:1272 with unchanged X/Y. ROM code stores attempted direction on collision and resets FF on success: 00 north, 01 south, 02 west, 03 east. The old 7E:3586 mapping is unsupported. |
| confirmed | SelectedDungeonToolCode | 0x02D1A | 7E:0A06, 7E:0A07 | Bomb selection matched A8 01 and ASCII name Bomb at 7E:0B77. |
| confirmed | DungeonToolActionState | 0x02CBC | 7E:09A8 | Bomb lifecycle matched 00 idle, 77 placed, 7F explosion, 00 idle. |
| confirmed | NpcDialogIndicator |  | 7E:099B, 7E:099C | Two NPCs matched 0000 -> 8801 -> 0000; an open shop remained 0000. |
| confirmed | SaveSelectionCursor | 0xA32454-0xA32455 | 7E:0108, 7E:0109 | All seven visible cursor positions atomically matched value and companion byte. |
| partially_confirmed | NameEntryCursor | 0xA32414-0xA32415 | 7E:0100, 7E:0101 | Live candidate; not every name-grid position has been exercised. |

## Quellenabdeckung

| Quelle | extrahierte Adressbehauptungen |
|---|---:|
| `data/emulator_addresses.json` | 79 |
| `data/shop_addresses.json` | 132 |
| `data/dungeon_flags_snes9x.json` | 76 |
| `data/dungeon_flags_snes9x-nwa.json` | 76 |
| `data/ram_map.json` | 350 |
| `data/ram_mappings/ram_static_offsets.json` | 30 |
| `data/ram_mappings/ram_volatile_stats.json` | 13 |
| `data/ram_mappings/rom_pointers.json` | 7 |
| `docs/lufia2_wram_checklist_merged_update_v5.txt` | 3361 |
| `emulator/csharp_helper/Core/Lufia2MemoryMap.cs` | 121 |
| `emulator/csharp_helper/Core/DataReaders.cs` | 58 |

Die vollständige Rohmatrix mit JSON-Pfad beziehungsweise Zeilennummer steht in `data/lufia2_wram_base_of_truth.json`. Dadurch geht auch bei widerlegten oder noch nicht getesteten Altangaben nichts verloren.
