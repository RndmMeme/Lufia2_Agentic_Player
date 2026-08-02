namespace Lufia2AutoTracker.Helper.Core
{
    /// <summary>
    /// Lufia II addresses used by the legacy Snes9x process helper plus a
    /// separately live-validated Mesen map. Despite its historic name, Wram
    /// below is a Snes9x host-mirror layout and must not be passed directly to
    /// Mesen's snesWorkRam API.
    /// </summary>
    public static class Lufia2MemoryMap
    {
        public static class Wram
        {
            public const int SnesBusBase = 0x7E0000;
            public const int Size = 0x20000;

            public static int FromSnesAddress(int address)
            {
                int offset = address - SnesBusBase;
                if (offset < 0 || offset >= Size)
                    throw new System.ArgumentOutOfRangeException(nameof(address));
                return offset;
            }

            public static int ToSnesAddress(int offset)
            {
                if (offset < 0 || offset >= Size)
                    throw new System.ArgumentOutOfRangeException(nameof(offset));
                return SnesBusBase + offset;
            }

            public const int Gold = 0x2D9E;

            public const int PartyStart = 0x2D8F;
            public const int PartyCount = 4;

            public const int InventoryStart = 0x2DA1;
            public const int InventoryLength = 0xC0;

            public const int ScenarioStart = 0x2C32;
            public const int ScenarioLength = 3;

            public const int CapsuleStart = 0x34CF;
            public const int CapsuleCount = 7;

            public const int DungeonFlagsStart = 0x2A96;
            public const int DungeonFlagsLength = 10;

            public const int Transport = 0x2CF5;

            public const int ShipXLow = 0x379C;
            public const int ShipXHigh = 0x379D;
            public const int ShipYLow = 0x379F;
            public const int ShipYHigh = 0x37A0;

            public const int WalkXLow = 0x377F;
            public const int WalkXHigh = 0x3780;
            public const int WalkYLow = 0x3782;
            public const int WalkYHigh = 0x3783;

            // Snes9x host-mirror offset. The corresponding true Mesen
            // snesWorkRam offset is MesenWram.CurrentMap (0x05AC).
            public const int Map = 0x28C0;
            public const int PreviousMap = 0x28C2;

            public const int DungeonX = 0x3532;
            public const int DungeonY = 0x353A;
            public const int DungeonBlocking = 0x3586;
            public const int MapContext = 0x2CBB;
            public const int ExplorationMode = 0x2CBD;
            public const int BattleMode = 0x2CBE;
            public const int FacingContact = 0x2CB5;
            public const int DungeonAxisMirrorX = 0x2368;
            public const int DungeonAxisMirrorY = 0x236E;
            public const int DungeonAxisChunkY = 0x236F;

            public const int CharacterBase = 0x2EBE;
            public const int CharacterStride = 0xBE;
            public const int CharacterLevel = 0x11;
            public const int CharacterStatus = 0x12;
            public const int CharacterCurrentHp = 0x14;
            public const int CharacterCurrentMp = 0x16;
            public const int CharacterMaxHp = 0x28;
            public const int CharacterMaxMp = 0x2A;
            public const int CharacterSpellsStart = 0x99;
            public const int CharacterSpellsLength = 0x24;
            public const int CharacterIp = 0xBF;

            public const int EnemyStructBase = 0x392C;
            public const int EnemyStride = 0xBE;
            public const int EnemyCount = 6;
            public const int EnemyName = 0x03;
            public const int EnemyNameLength = 13;
            public const int EnemyId = 0x53;
            public const int EnemyLevel = 0x11;
            public const int EnemyStatus = 0x12;
            public const int EnemyCurrentHp = 0x14;
            public const int EnemyCurrentMp = 0x16;
            public const int EnemyMaxHp = 0x28;
            public const int EnemyMaxMp = 0x2A;
            public const int EnemyAttack = 0x2C;
            public const int EnemyDefense = 0x2E;
            public const int EnemyStrength = 0x30;
            public const int EnemyAgility = 0x32;
            public const int EnemyIntelligence = 0x34;
            public const int EnemyGuts = 0x36;
            public const int EnemyMagicResistance = 0x38;
            public const byte CombatStatusPoison = 0x01;
            public const byte CombatStatusSilence = 0x02;
            public const byte CombatStatusDisabled = 0x04;
            public const byte CombatStatusParalyze = 0x08;
            public const byte CombatStatusConfusion = 0x10;
            public const byte CombatStatusSleep = 0x20;

            // Static randomizer strings used only to discover a candidate root.
            public const int SelanAnchor = 0x2F7E;
            public const int ArtyAnchor = 0x30FE;
            public const int LexisAnchor = 0x3326;
        }

        /// <summary>
        /// True offsets in Mesen 2.1.1's 128 KiB snesWorkRam image.
        /// Confirmed with visible UI values and controlled movement on
        /// 2026-07-26.
        /// </summary>
        public static class MesenWram
        {
            public const int Size = 0x20000;
            public const int LegacyHelperDelta = 0x2314;

            public const int Gold = 0x0A8A;
            public const int PartyStart = 0x0A7B;
            public const int PartyCount = 4;
            public const int InventoryStart = 0x0A8D;
            public const int InventoryLength = 0xC0;

            public const int ScenarioStart = 0x091E;
            public const int ScenarioLength = 3;
            public const int CapsuleStart = 0x11BB;
            public const int CapsuleCount = 7;
            public const int DungeonFlagsStart = 0x0782;
            public const int DungeonFlagsLength = 10;
            public const int Transport = 0x09E1;
            // uint8 map/floor ID. Resolve its parent zone through zones.txt;
            // e.g. zone 06 contains map/floor IDs 06 and 07.
            public const int CurrentMap = 0x05AC;
            // uint8 map/floor ID from which the actor entered CurrentMap.
            public const int PreviousMap = 0x05AE;

            public const int ShipXLow = 0x1488;
            public const int ShipXHigh = 0x1489;
            public const int ShipYLow = 0x148B;
            public const int ShipYHigh = 0x148C;
            public const int WalkXLow = 0x146B;
            public const int WalkXHigh = 0x146C;
            public const int WalkYLow = 0x146E;
            public const int WalkYHigh = 0x146F;

            // PPU background scroll mirrors, not logical player coordinates.
            public const int Bg1ScrollX = 0x0594;
            public const int Bg1ScrollY = 0x0596;
            public const int TownX = Bg1ScrollX; // Legacy compatibility alias.
            public const int TownY = Bg1ScrollY; // Legacy compatibility alias.
            public const int DungeonX = 0x121E;
            public const int DungeonY = 0x1226;
            public const int DungeonAxisMirrorX = 0x0054;
            public const int DungeonAxisMirrorY = 0x005A;
            public const int FacingHistory = 0x09A1;
            public const int MapContext = 0x09A7;
            public const int ExplorationMode = 0x09A9;
            public const int BattleMode = 0x09AA;
            public const int NpcDialogIndicator = 0x099B;
            public const int NpcDialogIndicatorLength = 2;
            public const int SelectedDungeonToolCode = 0x0A06;
            public const int DungeonToolActionState = 0x09A8;

            public const int DungeonActorCount = 0x28;
            public const int DungeonActorSpriteBase = 0x05D2;
            public const int DungeonActorMovementStateBase = 0x066A;
            public const int DungeonActorDirectionBase = 0x0692;
            public const int DungeonActorTileXBase = 0x06BA;
            public const int DungeonActorTileYBase = 0x06E2;
            public const int DungeonActorMovementModeBase = 0x070A;
            public const int DungeonActorFacingBase = 0x1E466;
            public const int DungeonBlockedDirection = 0x1272;
            public const byte DungeonActorEmptySprite = 0xFF;
            public const byte DungeonActorSpecialSprite = 0xFE;
            public const byte DungeonActorMovementActiveMask = 0x01;
            public const byte DungeonActorDirectionSouth = 0x00;
            public const byte DungeonActorDirectionWest = 0x02;
            public const byte DungeonActorDirectionNorth = 0x04;
            public const byte DungeonActorDirectionEast = 0x06;
            public const byte DungeonBlockedClear = 0xFF;
            public const byte DungeonActorFacingMask = 0x03;
            public const byte DungeonFacingNorth = 0x00;
            public const byte DungeonFacingSouth = 0x01;
            public const byte DungeonFacingWest = 0x02;
            public const byte DungeonFacingEast = 0x03;

            public const int EnemyStructBase = 0x1618;
            public const int EnemyStride = 0xBE;
            public const int EnemyCount = 6;
            public const int EnemyName = 0x03;
            public const int EnemyNameLength = 13;
            public const int EnemyId = 0x53;
            public const int EnemyLevel = 0x11;
            public const int EnemyStatus = 0x12;
            public const int EnemyCurrentHp = 0x14;
            public const int EnemyCurrentMp = 0x16;
            public const int EnemyMaxHp = 0x28;
            public const int EnemyMaxMp = 0x2A;
            public const int EnemyAttack = 0x2C;
            public const int EnemyDefense = 0x2E;
            public const int EnemyStrength = 0x30;
            public const int EnemyAgility = 0x32;
            public const int EnemyIntelligence = 0x34;
            public const int EnemyGuts = 0x36;
            public const int EnemyMagicResistance = 0x38;
            public const byte CombatStatusPoison = 0x01;
            public const byte CombatStatusSilence = 0x02;
            public const byte CombatStatusDisabled = 0x04;
            public const byte CombatStatusParalyze = 0x08;
            public const byte CombatStatusConfusion = 0x10;
            public const byte CombatStatusSleep = 0x20;

            public const int BattlePartyCommandBase = 0x1F560;
            public const int BattlePartyCommandStride = 0x0C;
            public const int BattlePartyTargetMask = 0x00;
            public const int BattlePartyCommand = 0x04;
            public const int BattlePartySelectedAction = 0x06;
            public const int BattlePartyActorMask = 0x0A;
            public const int BattleActiveTargetIndex = 0x0026;
            public const byte BattleEnemyTargetFlag = 0x80;
            public const int BattleEnemyTargetCount = 6;
            public const int BattleHumanTargetCount = 4;
            public const int BattleAllyTargetCount = 5;
            public const byte BattleCapsuleTargetMask = 0x10;
            public const int BattleInitiativeQueueBase = 0x01B8C;
            public const int BattleInitiativeQueueStride = 0x03;
            public const int BattleInitiativeQueueMaxActors = 11;
            public const int BattleInitiativeActorMask = 0x00;
            public const int BattleInitiativeValue = 0x01;
            public const int BattleActiveActionBase = 0x1F44E;
            public const int BattleActiveActionActorMask = 0x00;
            public const int BattleActiveActionTargetMask = 0x02;
            public const int BattleActiveActionCommand = 0x06;
            public const int BattleActiveActionId = 0x0A;
            public const byte BattleCommandAttack = 0x01;
            public const byte BattleCommandMagic = 0x02;
            public const byte BattleCommandItem = 0x03;
            public const byte BattleCommandDefend = 0x04;
            public const byte BattleCommandIp = 0x08;

            public const int BattleGroupMenuSelection = 0x0B4E;
            public const byte BattleGroupFight = 0x09;
            public const byte BattleGroupTradePositions = 0x0A;
            public const byte BattleGroupEscape = 0x0B;
            public const int BattleFormationStart = 0x153D;
            public const int BattleFormationCount = 4;
            public const int BattleRewardExp = 0x1605;
            public const int BattleRewardGold = 0x1608;

            public const int BattleIpCursorIndex = 0x0014;
            public const int BattleIpCursorY = 0x0101;
            public const int BattleIpEquipmentList = 0x1357;
            public const int BattleIpEquipmentCount = 6;
            public const int BattleIpPromptPane = 0x3046;
            public const int BattleIpFirstRenderedRow = 0x3147;
            public const int BattleIpRenderedRowStride = 0x80;
            public const int BattleIpNameOffsetInRow = 0x1B;
            public const int BattleIpAvailabilityAttributeOffsetInRow = 0x02;
            public const byte BattleIpAvailableAttribute = 0x20;
            public const byte BattleIpInsufficientAttribute = 0x24;
            public const int BattleIpRenderedPaneEnd = 0x3447;

            public const int BattleMagicWindowFirstIndex = 0x0011;
            public const int BattleMagicSelectedAbsoluteIndex = 0x0012;
            public const int BattleMagicSelectedColumn = 0x0013;
            public const int BattleMagicSelectedVisibleRow = 0x0014;
            public const int BattleMagicCursorX = 0x0100;
            public const int BattleMagicCursorY = 0x0101;
            public const int BattleMagicPromptPane = 0x3046;
            public const int BattleMagicFirstRenderedRow = 0x3146;
            public const int BattleMagicRenderedRowStride = 0x80;
            public const int BattleMagicRightColumnOffset = 0x1C;
            public const int BattleMagicAvailabilityAttributeOffset = 0x01;
            public const byte BattleMagicAvailableAttribute = 0x20;
            public const byte BattleMagicDisabledAttribute = 0x24;
            public const int CharacterSpellSlotCount = 36;
            public const byte EmptySpellSlot = 0xFF;

            public const int BattleItemWindowFirstByteOffset = 0x0011;
            public const int BattleItemSelectedInventoryByteOffset = 0x0012;
            public const int BattleItemSelectedVisibleRow = 0x0014;
            public const int BattleItemCursorX = 0x0100;
            public const int BattleItemCursorY = 0x0101;
            public const int BattleItemPromptPane = 0x3046;
            public const int BattleItemFirstRenderedRow = 0x3147;
            public const int BattleItemRenderedRowStride = 0x80;
            public const int BattleItemAvailabilityAttributeOffset = 0x02;
            public const byte BattleItemAvailableAttribute = 0x20;
            public const byte BattleItemDisabledAttribute = 0x24;
            public const int InventorySlotCount = 96;

            public const int SelectedShopItemName = 0x0B77;
            public const int SelectedShopItemNameLength = 18;
            public const int SelectedShopItemPrice = 0x0B89;
            public const int ShopCursorPosition = 0x1574;

            public const int CharacterBase = 0x0BAA;
            public const int CharacterStride = 0xBE;
            public const int CharacterLevel = 0x11;
            public const int CharacterStatus = 0x12;
            public const int CharacterCurrentHp = 0x14;
            public const int CharacterCurrentMp = 0x16;
            public const int CharacterMaxHp = 0x28;
            public const int CharacterMaxMp = 0x2A;
            public const int CharacterSpellsStart = 0x99;
            public const int CharacterSpellsLength = 0x24;
            public const int CharacterIp = 0xBF;

            public const int SaveSelectionCursor = 0x0108;
            public const int NameEntryCursor = 0x0100;
        }

        public static class Rom
        {
            public const int InternalHeader = 0xFFC0;
            public const int CapsuleSpriteTable = 0xBDCB8;
            public const int CapsuleSpriteStride = 10;
            public const int CapsuleSpriteCount = 7;
        }
    }
}
