using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using BepInEx.Logging;
using HarmonyLib;
using TMPro;
using UnityEngine;

namespace RTLC.BABBDI.RussianTranslate
{
    internal sealed class FontFallbacks
    {
        private static readonly HashSet<string> MonoStyledTmpFonts = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "Menu",
            "Title",
            "Title 1",
            "Title 2",
            "ContinueDialogueFX",
            "SavePopup",
            "SecretPopup",
            "TabSecret",
        };

        private readonly ManualLogSource _logger;
        private readonly HashSet<int> _configuredFonts = new HashSet<int>();
        private TMP_FontAsset _sansFallback;
        private TMP_FontAsset _monoFallback;
        private TMP_FontAsset _majorCyrillic;
        private TMP_FontAsset _futuraCyrillic;
        private readonly AssetBundle _bundle;
        private bool _fallbacksCreated;

        public TMP_FontAsset MajorCyrillic => _majorCyrillic;

        public FontFallbacks(ManualLogSource logger, AssetBundle bundle)
        {
            _logger = logger;
            _bundle = bundle;
        }

        public bool ApplyToLoadedFonts()
        {
            TMP_FontAsset[] fontAssets = Resources.FindObjectsOfTypeAll<TMP_FontAsset>();
            if (!_fallbacksCreated)
                CreateFallbacks();

            if (_sansFallback == null && _monoFallback == null && _majorCyrillic == null && _futuraCyrillic == null)
                return false;

            bool changed = false;

            foreach (TMP_FontAsset fontAsset in fontAssets)
            {
                if (fontAsset == null)
                    continue;
                if (fontAsset.name.StartsWith("RTLC Cyrillic ", StringComparison.Ordinal))
                    continue;
                if (!_configuredFonts.Add(fontAsset.GetInstanceID()))
                    continue;

                try
                {
                    IList fallbackList = GetOrCreateFallbackList(fontAsset);
                    if (fallbackList == null)
                        continue;

                    bool preferMono = MonoStyledTmpFonts.Contains(fontAsset.name);
                    TMP_FontAsset styled = preferMono ? _majorCyrillic :
                        string.Equals(fontAsset.name, "FuturaHandwritten SDF", StringComparison.OrdinalIgnoreCase) ? _futuraCyrillic : null;
                    if (styled != null && !fallbackList.Contains(styled))
                    {
                        fallbackList.Insert(0, styled);
                        changed = true;
                        _logger.LogInfo("Connected " + styled.name + " to " + fontAsset.name + ".");
                    }

                    TMP_FontAsset primary =  preferMono ? _monoFallback : _sansFallback;
                    TMP_FontAsset secondary = preferMono ? _sansFallback : _monoFallback;

                    if (primary != null && !fallbackList.Contains(primary))
                    {
                        fallbackList.Add(primary);
                        changed = true;
                    }
                    if (secondary != null && !fallbackList.Contains(secondary))
                    {
                        fallbackList.Add(secondary);
                        changed = true;
                    }
                }
                catch (Exception exception)
                {
                    _logger.LogDebug("Could not add Cyrillic font fallback to " + fontAsset.name + ": " + exception.Message);
                }
            }

            return changed;
        }

        private void CreateFallbacks()
        {
            _fallbacksCreated = true;
            _majorCyrillic = LoadCustomFont("MajorMonoDisplay-Cyrillic-Final-Regular.ttf");
            _futuraCyrillic = LoadCustomFont("FuturaHandwritten-Cyrillic-Regular.ttf");
            Font[] fonts = Resources.FindObjectsOfTypeAll<Font>();
            var candidates = fonts
                .Where(font => font != null)
                .OrderBy(font => font.name, StringComparer.OrdinalIgnoreCase)
                .ToList();

            foreach (Font font in candidates)
            {
                string name = font.name ?? string.Empty;
                if (_sansFallback == null && name.IndexOf("LiberationSans", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    _sansFallback = CreateDynamicAsset(font);
                }
                else if (_monoFallback == null && name.IndexOf("monofonto", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    _monoFallback = CreateDynamicAsset(font);
                }
            }

            if (_sansFallback == null)
            {
                try
                {
                    Font arial = Font.CreateDynamicFontFromOSFont("Arial", 48);
                    _sansFallback = CreateDynamicAsset(arial);
                }
                catch (Exception exception)
                {
                    _logger.LogWarning("Could not create a Cyrillic fallback font: " + exception.Message);
                }
            }

            int createdCount = (_majorCyrillic != null ? 1 : 0) + (_futuraCyrillic != null ? 1 : 0) + (_sansFallback != null ? 1 : 0) + (_monoFallback != null ? 1 : 0);
            _logger.LogInfo(createdCount == 0
                ? "No dynamic Cyrillic font fallback could be created; the game may show missing glyphs."
                : "Created " + createdCount + " dynamic Cyrillic TMP font fallback(s).");
        }

        private TMP_FontAsset LoadCustomFont(string fileName)
        {
            try
            {
                var font = _bundle.LoadAsset<Font>("assets/rtlc/" + fileName.ToLowerInvariant());
                if (font == null)
                    throw new InvalidOperationException("Font is missing from rtlc.bundle.");

                var asset = CreateDynamicAsset(font);
                if (asset != null && asset.TryAddCharacters("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя"))
                {
                    font.hideFlags = HideFlags.DontUnloadUnusedAsset;
                    _logger.LogInfo("Loaded Cyrillic font " + fileName + ".");
                    return asset;
                }

                if (asset != null)
                    UnityEngine.Object.Destroy(asset);

                _logger.LogWarning("Could not render all Russian letters from " + fileName + ".");
            }
            catch (Exception exception)
            {
                _logger.LogWarning("Could not load " + fileName + ": " + exception.Message);
            }

            return null;
        }

        private TMP_FontAsset CreateDynamicAsset(Font font)
        {
            if (font == null)
                return null;

            try
            {
                var create = AccessTools.Method(typeof(TMP_FontAsset), "CreateFontAsset", new[] { typeof(Font) });
                if (create == null)
                {
                    _logger.LogWarning("This TextMeshPro version does not expose TMP_FontAsset.CreateFontAsset(Font).");
                    return null;
                }

                var asset = create.Invoke(null, new object[] { font }) as TMP_FontAsset;
                if (asset == null)
                    return null;

                asset.name = "RTLC Cyrillic " + font.name;
                asset.hideFlags = HideFlags.DontUnloadUnusedAsset;

                var populationProperty = AccessTools.Property(typeof(TMP_FontAsset), "atlasPopulationMode");
                if (populationProperty != null && populationProperty.PropertyType.IsEnum)
                    populationProperty.SetValue(asset, Enum.Parse(populationProperty.PropertyType, "Dynamic"), null);

                return asset;
            }
            catch (Exception exception)
            {
                _logger.LogDebug("Could not create TMP fallback from " + font.name + ": " + exception.Message);
                return null;
            }
        }

        private static IList GetOrCreateFallbackList(TMP_FontAsset asset)
        {
            var property = AccessTools.Property(typeof(TMP_FontAsset), "fallbackFontAssetTable");
            if (property != null)
            {
                IList propertyList = property.GetValue(asset, null) as IList;
                if (propertyList == null)
                {
                    propertyList = Activator.CreateInstance(property.PropertyType) as IList;
                    if (propertyList != null)
                        property.SetValue(asset, propertyList, null);
                }
                return propertyList;
            }

            var field = AccessTools.Field(typeof(TMP_FontAsset), "m_FallbackFontAssetTable");
            if (field == null)
                return null;

            IList list = field.GetValue(asset) as IList;
            if (list != null)
                return list;

            Type listType = field.FieldType;
            list = Activator.CreateInstance(listType) as IList;
            if (list != null)
                field.SetValue(asset, list);
            return list;
        }
    }
}
