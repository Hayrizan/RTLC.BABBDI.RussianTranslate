using System;
using System.Collections.Generic;
using System.IO;
using BepInEx.Logging;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace RTLC.BABBDI.RussianTranslate
{
    internal sealed class TextureManifestEntry
    {
        public string file = string.Empty;
        public string name = string.Empty;
        public bool contains = false;
        public int width = 0;
        public int height = 0;
    }

    internal sealed class TextureOverrides
    {
        private readonly AssetBundle _bundle;
        private readonly ManualLogSource _logger;
        private readonly HashSet<int> _replaced = new HashSet<int>();
        private readonly Dictionary<string, List<LoadedOverride>> _exactOverrides =
            new Dictionary<string, List<LoadedOverride>>(StringComparer.OrdinalIgnoreCase);
        private readonly List<LoadedOverride> _containsOverrides = new List<LoadedOverride>();

        public TextureOverrides(AssetBundle bundle, ManualLogSource logger)
        {
            _bundle = bundle;
            _logger = logger;
            LoadManifest();
        }

        public void BeginScene()
        {
            // Unity can reuse instance IDs after unloading the previous scene.
            _replaced.Clear();
        }

        public void ApplyLoadedTextures()
        {
            if (_exactOverrides.Count == 0 && _containsOverrides.Count == 0)
                return;

            foreach (Texture2D texture in Resources.FindObjectsOfTypeAll<Texture2D>())
            {
                if (texture == null)
                    continue;

                int instanceId = texture.GetInstanceID();
                if (_replaced.Contains(instanceId))
                    continue;

                LoadedOverride matched = FindMatch(texture);
                if (matched == null)
                    continue;

                try
                {
                    // Mark replaced textures non-readable so Unity uploads pixels directly to GPU
                    // without keeping a duplicate CPU-side image.
                    if (ImageConversion.LoadImage(texture, matched.Bytes, true))
                    {
                        _replaced.Add(instanceId);
                        _logger.LogInfo("Applied Russian texture: " + texture.name + " (" + texture.width + "x" + texture.height + ").");
                    }
                    else
                    {
                        _logger.LogWarning("Unity could not load texture override for " + texture.name + ".");
                    }
                }
                catch (Exception exception)
                {
                    _logger.LogWarning("Texture override failed for " + texture.name + ": " + exception.Message);
                }
            }
        }

        private LoadedOverride FindMatch(Texture2D texture)
        {
            string texName = texture.name;
            int width = texture.width;
            int height = texture.height;

            if (!string.IsNullOrEmpty(texName) && _exactOverrides.TryGetValue(texName, out List<LoadedOverride> exactList))
            {
                for (int i = 0; i < exactList.Count; i++)
                {
                    TextureManifestEntry entry = exactList[i].Entry;
                    if (entry.width == width && entry.height == height)
                        return exactList[i];
                }
            }

            if (!string.IsNullOrEmpty(texName))
            {
                for (int i = 0; i < _containsOverrides.Count; i++)
                {
                    TextureManifestEntry entry = _containsOverrides[i].Entry;
                    if (entry.width == width &&
                        entry.height == height &&
                        texName.IndexOf(entry.name, StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        return _containsOverrides[i];
                    }
                }
            }

            return null;
        }

        private void LoadManifest()
        {
            int loadedCount = 0;
            try
            {
                JObject manifest = JObject.Parse(_bundle.LoadAsset<TextAsset>("assets/rtlc/texture_manifest.bytes").text);
                JArray textures = manifest["textures"] as JArray;
                if (textures == null)
                    return;

                foreach (JToken item in textures)
                {
                    var entry = new TextureManifestEntry
                    {
                        file = (string)item["file"] ?? string.Empty,
                        name = (string)item["name"] ?? string.Empty,
                        contains = (bool?)item["contains"] ?? false,
                        width = (int?)item["width"] ?? 0,
                        height = (int?)item["height"] ?? 0
                    };
                    if (string.IsNullOrWhiteSpace(entry.file) || string.IsNullOrWhiteSpace(entry.name))
                        continue;

                    var image = _bundle.LoadAsset<TextAsset>("assets/rtlc/textures/" + entry.file);
                    if (image == null)
                    {
                        _logger.LogWarning("Texture override file is missing: " + entry.file);
                        continue;
                    }

                    var loaded = new LoadedOverride(entry, image.bytes);
                    if (entry.contains)
                    {
                        _containsOverrides.Add(loaded);
                    }
                    else
                    {
                        if (!_exactOverrides.TryGetValue(entry.name, out List<LoadedOverride> list))
                        {
                            list = new List<LoadedOverride>(1);
                            _exactOverrides[entry.name] = list;
                        }
                        list.Add(loaded);
                    }
                    loadedCount++;
                }
            }
            catch (Exception exception)
            {
                _logger.LogError("Could not load texture_manifest.json: " + exception.Message);
            }

            _logger.LogInfo("Loaded " + loadedCount + " Russian texture overrides.");
        }

        private sealed class LoadedOverride
        {
            public readonly TextureManifestEntry Entry;
            public readonly byte[] Bytes;

            public LoadedOverride(TextureManifestEntry entry, byte[] bytes)
            {
                Entry = entry;
                Bytes = bytes;
            }
        }
    }
}
