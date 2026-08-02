using System.Text.Json.Serialization;

namespace Lufia2AutoTracker.Helper.Core
{
    [JsonSourceGenerationOptions(
        PropertyNameCaseInsensitive = true,
        PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
    [JsonSerializable(typeof(RootHintDocument))]
    [JsonSerializable(typeof(GameState))]
    [JsonSerializable(typeof(PartyStat))]
    [JsonSerializable(typeof(RawInventorySlot))]
    [JsonSerializable(typeof(TrackerStatusEnvelope))]
    internal partial class TrackerJsonContext : JsonSerializerContext
    {
    }
}
