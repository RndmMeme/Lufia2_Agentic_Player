using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Lufia2AutoTracker.Helper.Core
{
    public sealed record PartyStat
    {
        [JsonPropertyName("level")]
        public int Level { get; init; }
        [JsonPropertyName("status")]
        public int Status { get; init; }
        [JsonPropertyName("hp")]
        public int Hp { get; init; }
        [JsonPropertyName("max_hp")]
        public int MaxHp { get; init; }
        [JsonPropertyName("mp")]
        public int Mp { get; init; }
        [JsonPropertyName("max_mp")]
        public int MaxMp { get; init; }
        [JsonPropertyName("ip")]
        public int Ip { get; init; }
        [JsonPropertyName("spells")]
        public List<int> Spells { get; init; } = new();
        [JsonPropertyName("ip_attacks")]
        public List<string> IpAttacks { get; init; } = new();
    }

    public sealed record RawInventorySlot
    {
        [JsonPropertyName("slot")]
        public int Slot { get; init; }
        [JsonPropertyName("byte1")]
        public int Byte1 { get; init; }
        [JsonPropertyName("byte2")]
        public int Byte2 { get; init; }
    }

    public sealed record EnemyStat
    {
        [JsonPropertyName("slot")]
        public int Slot { get; init; }
        [JsonPropertyName("name")]
        public string Name { get; init; } = string.Empty;
        [JsonPropertyName("id")]
        public int Id { get; init; }
        [JsonPropertyName("level")]
        public int Level { get; init; }
        [JsonPropertyName("status")]
        public int Status { get; init; }
        [JsonPropertyName("hp")]
        public int Hp { get; init; }
        [JsonPropertyName("mp")]
        public int Mp { get; init; }
        [JsonPropertyName("max_hp")]
        public int MaxHp { get; init; }
        [JsonPropertyName("max_mp")]
        public int MaxMp { get; init; }
        [JsonPropertyName("attack")]
        public int Attack { get; init; }
        [JsonPropertyName("defense")]
        public int Defense { get; init; }
        [JsonPropertyName("strength")]
        public int Strength { get; init; }
        [JsonPropertyName("agility")]
        public int Agility { get; init; }
        [JsonPropertyName("intelligence")]
        public int Intelligence { get; init; }
        [JsonPropertyName("guts")]
        public int Guts { get; init; }
        [JsonPropertyName("magic_resistance")]
        public int MagicResistance { get; init; }
    }

    public class GameState
    {
        [JsonPropertyName("inventory")]
        public List<string>? Inventory { get; set; } = new List<string>();

        [JsonPropertyName("characters")]
        public List<string>? Characters { get; set; } = new List<string>();

        [JsonPropertyName("capsules")]
        public List<string>? Capsules { get; set; } = new List<string>();

        [JsonPropertyName("capsule_sprite_values")]
        public List<string>? CapsuleSpriteValues { get; set; } = new List<string>();

        [JsonPropertyName("player_x")]
        public int PlayerX { get; set; }

        [JsonPropertyName("player_y")]
        public int PlayerY { get; set; }

        [JsonPropertyName("transport_mode")]
        public string TransportMode { get; set; } = string.Empty;

        [JsonPropertyName("cleared_locations")]
        public List<string>? ClearedLocations { get; set; } = new List<string>();

        [JsonPropertyName("scenario")]
        public List<string>? ScenarioItems { get; set; } = new List<string>();

        [JsonPropertyName("maidens")]
        public Dictionary<string, bool>? Maidens { get; set; } = new Dictionary<string, bool>();

        [JsonPropertyName("spoiler_log")]
        public List<Dictionary<string, string>>? SpoilerLog { get; set; } = new List<Dictionary<string, string>>();

        [JsonPropertyName("gold")]
        public int Gold { get; set; }
        [JsonPropertyName("map_id")]
        public int MapId { get; set; }
        [JsonPropertyName("previous_map_id")]
        public int PreviousMapId { get; set; }
        [JsonPropertyName("party_stats")]
        public List<PartyStat>? PartyStats { get; set; } = new();
        [JsonPropertyName("raw_inventory")]
        public List<RawInventorySlot>? RawInventory { get; set; } = new();
        [JsonPropertyName("enemy_hp_list")]
        public List<int>? EnemyHpList { get; set; } = new();
        [JsonPropertyName("enemy_stats")]
        public List<EnemyStat>? EnemyStats { get; set; } = new();
        [JsonPropertyName("dungeon_x")]
        public int DungeonX { get; set; }
        [JsonPropertyName("dungeon_y")]
        public int DungeonY { get; set; }
        [JsonPropertyName("dungeon_blocking")]
        public int DungeonBlocking { get; set; } = 255;
        [JsonPropertyName("map_context_flag")]
        public int MapContextFlag { get; set; }
        [JsonPropertyName("exploration_mode_flag")]
        public int ExplorationModeFlag { get; set; }
        [JsonPropertyName("battle_mode_flag")]
        public int BattleModeFlag { get; set; }
        [JsonPropertyName("facing_contact_state")]
        public int FacingContactState { get; set; }
        [JsonPropertyName("dungeon_axis_mirror_x")]
        public int DungeonAxisMirrorX { get; set; }
        [JsonPropertyName("dungeon_axis_mirror_y")]
        public int DungeonAxisMirrorY { get; set; }
        [JsonPropertyName("dungeon_axis_chunk_y")]
        public int DungeonAxisChunkY { get; set; }
        [JsonPropertyName("in_battle")]
        public bool InBattle { get; set; }
    }
}
