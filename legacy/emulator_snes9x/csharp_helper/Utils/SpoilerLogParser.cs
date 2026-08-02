using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Lufia2AutoTracker.Helper.Utils
{
    public static class SpoilerLogParser
    {
        public static List<Dictionary<string, string>> Parse(string content)
        {
            var results = new List<Dictionary<string, string>>();
            if (string.IsNullOrEmpty(content)) return results;

            // Basic regex-based parsing for Lufia 2 Randomizer spoiler logs
            // Logic: Find Location -> Item mappings
            // Example: [Location Name] : [Item Name]
            var matches = Regex.Matches(content, @"^(.+?)\s*:\s*(.+)$", RegexOptions.Multiline);
            foreach (Match match in matches)
            {
                if (match.Groups.Count >= 3)
                {
                    results.Add(new Dictionary<string, string>
                    {
                        { "location", match.Groups[1].Value.Trim() },
                        { "item", match.Groups[2].Value.Trim() }
                    });
                }
            }
            return results;
        }
    }
}
