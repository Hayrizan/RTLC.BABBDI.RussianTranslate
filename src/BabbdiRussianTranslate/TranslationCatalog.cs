using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using BepInEx.Logging;
using Newtonsoft.Json.Linq;

namespace RTLC.BABBDI.RussianTranslate
{
    internal sealed class TranslationCatalog
    {
        private const int MaxCacheSize = 512;

        private static readonly Regex CollectedSecrets = new Regex(
            @"^You collected (?<count>\d+)/21 secret objects\.$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);
        private static readonly Regex CompletedRun = new Regex(
            @"^You completed the game in (?<time>.+?) seconds\.$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

        private readonly Dictionary<string, string> _entries;
        private readonly Dictionary<string, string> _cache = new Dictionary<string, string>(256, StringComparer.Ordinal);

        private TranslationCatalog(Dictionary<string, string> entries)
        {
            _entries = entries;
        }

        public static TranslationCatalog Load(string json, ManualLogSource logger)
        {
            var entries = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(json))
            {
                logger.LogWarning("Translation catalog is missing from rtlc.bundle.");
                return new TranslationCatalog(entries);
            }

            try
            {
                JObject file = JObject.Parse(json);
                JArray entriesArray = file["entries"] as JArray;
                if (entriesArray != null)
                {
                    foreach (JToken entry in entriesArray)
                    {
                        string source = (string)entry["source"];
                        string target = (string)entry["target"];
                        if (string.IsNullOrEmpty(source) || target == null)
                            continue;
                        entries[source] = target;
                    }
                }
            }
            catch (Exception exception)
            {
                logger.LogError("Could not read translations.json: " + exception.Message);
            }

            logger.LogInfo("Loaded " + entries.Count + " Russian text translations.");
            return new TranslationCatalog(entries);
        }

        public string Translate(string text)
        {
            if (string.IsNullOrEmpty(text) || !ContainsAsciiLetter(text))
                return text;

            if (_cache.TryGetValue(text, out string cached))
                return cached;

            string translated = ComputeTranslation(text);
            if (_cache.Count >= MaxCacheSize)
                _cache.Clear();
            _cache[text] = translated;
            return translated;
        }

        private static bool ContainsAsciiLetter(string text)
        {
            for (int i = 0; i < text.Length; i++)
            {
                char c = text[i];
                if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))
                    return true;
            }
            return false;
        }

        private string ComputeTranslation(string text)
        {
            Match match = CollectedSecrets.Match(text);
            if (match.Success)
                return "Секретные предметы: " + match.Groups["count"].Value + "/21";

            match = CompletedRun.Match(text);
            if (match.Success)
                return "Игра пройдена за " + match.Groups["time"].Value + " сек.";

            int start = 0;
            while (start < text.Length && char.IsWhiteSpace(text[start]))
                start++;
            int end = text.Length;
            while (end > start && char.IsWhiteSpace(text[end - 1]))
                end--;

            if (start >= end)
                return text;

            string key = text.Substring(start, end - start);
            if (!TryGetTranslation(key, out string value, out string translatedSuffix))
            {
                int colonIndex = key.IndexOf(':');
                if (colonIndex <= 0)
                    return text;

                string label = key.Substring(0, colonIndex).TrimEnd();
                if (!TryGetTranslation(label, out value, out translatedSuffix))
                    return text;

                string suffix = key.Substring(colonIndex + 1);
                return text.Substring(0, start) + MatchCapitalization(label, value) + translatedSuffix + ":" + suffix + text.Substring(end);
            }

            return text.Substring(0, start) + MatchCapitalization(key, value) + translatedSuffix + text.Substring(end);
        }

        private static string MatchCapitalization(string source, string target)
        {
            if (source != source.ToUpperInvariant() || source == source.ToLowerInvariant())
                return target;

            // TMP markup is case sensitive in some tags. Preserve it verbatim.
            return Regex.Replace(target, "<[^>]+>|[^<]+", match =>
                match.Value[0] == '<' ? match.Value : match.Value.ToUpperInvariant());
        }

        private bool TryGetTranslation(string key, out string value, out string suffix)
        {
            if (_entries.TryGetValue(key, out value))
            {
                suffix = string.Empty;
                return true;
            }

            int digitStart = key.Length;
            while (digitStart > 0 && char.IsDigit(key[digitStart - 1]))
                digitStart--;

            int nameEnd = digitStart;
            while (nameEnd > 0 && char.IsWhiteSpace(key[nameEnd - 1]))
                nameEnd--;

            if (digitStart < key.Length && nameEnd > 0 && _entries.TryGetValue(key.Substring(0, nameEnd), out value))
            {
                suffix = key.Substring(nameEnd);
                return true;
            }

            value = null;
            suffix = string.Empty;
            return false;
        }
    }
}
