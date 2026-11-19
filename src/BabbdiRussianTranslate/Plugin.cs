using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using BepInEx;
using HarmonyLib;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace RTLC.BABBDI.RussianTranslate
{
    [BepInPlugin(PluginGuid, PluginName, PluginVersion)]
    public sealed class Plugin : BaseUnityPlugin
    {
        public const string PluginGuid = "net.rtlc.babbdi.russian";
        public const string PluginName = "BABBDI Russian Translation";
        public const string PluginVersion = "0.1.0";

        private static readonly float[] PostLoadScanOffsets = { 0.05f, 0.35f, 1.6f };
        private static readonly HashSet<string> PauseButtonParents = new HashSet<string>(StringComparer.Ordinal)
        {
            "Resume",
            "Library",
            "Controls",
            "Lobby",
            "ReturnOffice",
        };
        private static readonly HashSet<string> PauseButtonTexts = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "Продолжить",
            "Журнал",
            "Управление",
            "ВЕРНУТЬСЯ ДОМОЙ",
            "ВЕРНУТЬСЯ В ИНФОРМАЦИОННЫЙ ЦЕНТР",
        };

        private readonly Dictionary<int, float> _baseFontSizes = new Dictionary<int, float>();
        private readonly Dictionary<int, string> _fittedTexts = new Dictionary<int, string>();

        private readonly HashSet<int> _raisedOptionsButtons = new HashSet<int>();
        private AssetBundle _bundle;
        private Harmony _harmony;
        private TextureOverrides _textureOverrides;
        private FontFallbacks _fontFallbacks;
        private float _sceneLoadTime;
        private int _scanStep;

        private void Awake()
        {
            string pluginDirectory = Path.GetDirectoryName(Info.Location);
            if (string.IsNullOrEmpty(pluginDirectory))
                pluginDirectory = Path.Combine(Paths.PluginPath, "RTLC.BABBDI.RussianTranslate");
            _bundle = AssetBundle.LoadFromFile(Path.Combine(pluginDirectory, "rtlc.bundle"));
            if (_bundle == null)
            {
                Logger.LogError("Could not open rtlc.bundle.");
                enabled = false;
                return;
            }

            var catalog = TranslationCatalog.Load(
                _bundle.LoadAsset<TextAsset>("assets/rtlc/translations.bytes")?.text,
                Logger);
            TranslationPatches.Catalog = catalog;

            _harmony = new Harmony(PluginGuid);
            PatchTextSetter(typeof(TMPro.TMP_Text));
            PatchTextSetter(typeof(UnityEngine.UI.Text));
            PatchTextSetter(typeof(TextMesh));
            PatchTextSetTextMethods();
            PatchTypewriter();

            _textureOverrides = new TextureOverrides(_bundle, Logger);
            _fontFallbacks = new FontFallbacks(Logger, _bundle);
            SceneManager.sceneLoaded += OnSceneLoaded;

            _sceneLoadTime = Time.unscaledTime;
            _scanStep = 0;
            RunFullPass();

            Logger.LogInfo("BABBDI Russian Translation loaded. Text hooks are active; texture overrides are local in-memory replacements.");
        }

        private void Update()
        {
            if (_scanStep >= PostLoadScanOffsets.Length)
                return;

            if (Time.unscaledTime >= _sceneLoadTime + PostLoadScanOffsets[_scanStep])
            {
                _scanStep++;
                RunFullPass();
            }
        }

        private void OnDestroy()
        {
            SceneManager.sceneLoaded -= OnSceneLoaded;
            _harmony?.UnpatchSelf();
            TranslationPatches.Catalog = null;
            if (_bundle != null)
                _bundle.Unload(false);
        }

        private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            _baseFontSizes.Clear();
            _fittedTexts.Clear();
            _raisedOptionsButtons.Clear();
            _textureOverrides?.BeginScene();
            _sceneLoadTime = Time.unscaledTime;
            _scanStep = 0;
            RunFullPass();
        }

        private void RunFullPass()
        {
            if (_fontFallbacks?.ApplyToLoadedFonts() == true)
                RefreshLoadedTmpMeshes();
            TranslateLoadedText();
            FullscreenToggle.Install();
            if (HotelSign.Apply(out bool verticalInstalled))
                Logger.LogInfo("Installed Russian hotel lettering.");
            if (verticalInstalled)
                Logger.LogInfo("Installed Russian vertical hotel sign.");
            _textureOverrides?.ApplyLoadedTextures();
        }

        private void RefreshLoadedTmpMeshes()
        {
            foreach (var label in Resources.FindObjectsOfTypeAll<TMPro.TMP_Text>())
            {
                if (label == null || !label.gameObject.scene.IsValid())
                    continue;

                try
                {
                    label.ForceMeshUpdate();
                }
                catch (Exception exception)
                {
                    Logger.LogDebug("Could not refresh TMP text after adding Cyrillic fallbacks: " + exception.Message);
                }
            }
        }

        private void PatchTextSetter(Type type)
        {
            var setter = AccessTools.PropertySetter(type, "text");
            if (setter == null)
            {
                Logger.LogWarning("Could not find text setter on " + type.FullName + ".");
                return;
            }

            _harmony.Patch(setter, prefix: new HarmonyMethod(typeof(TranslationPatches), nameof(TranslationPatches.TranslateTextArgument)));
        }

        private void PatchTypewriter()
        {
            Type type = AccessTools.TypeByName("TypewriterEffect");
            var method = type == null ? null : AccessTools.Method(type, "Run", new[] { typeof(string), typeof(TMPro.TMP_Text) });
            if (method == null)
            {
                Logger.LogWarning("TypewriterEffect.Run was not found; dialogue will still be translated when assigned to TMP text.");
                return;
            }

            _harmony.Patch(method, prefix: new HarmonyMethod(typeof(TranslationPatches), nameof(TranslationPatches.TranslateTextArgument)));
        }

        private void PatchTextSetTextMethods()
        {
            const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly;
            foreach (MethodInfo method in typeof(TMPro.TMP_Text).GetMethods(flags))
            {
                if (method.Name != "SetText")
                    continue;

                ParameterInfo[] parameters = method.GetParameters();
                if (parameters.Length == 0 || parameters[0].ParameterType != typeof(string))
                    continue;

                _harmony.Patch(method, prefix: new HarmonyMethod(typeof(TranslationPatches), nameof(TranslationPatches.TranslateTextArgument)));
            }
        }

        private void TranslateLoadedText()
        {
            TranslationCatalog catalog = TranslationPatches.Catalog;
            if (catalog == null)
                return;

            foreach (var label in Resources.FindObjectsOfTypeAll<TMPro.TMP_Text>())
            {
                if (label == null || !label.gameObject.scene.IsValid())
                    continue;
                string translated = catalog.Translate(label.text);
                if (!string.Equals(label.text, translated, StringComparison.Ordinal))
                    label.text = translated;
                LocalizeLogo(label);
                if ((label.name == "LoaderText" && label.text?.Trim() == "ЗА Г Р\nУ З А К") ||
                    label.text?.Trim() == "СОХРАНЕНИЕ...")
                {
                    UseMajorCyrillic(label);
                    label.enableWordWrapping = false;
                }
                FitUiLabel(label);
                var parent = label.transform.parent as RectTransform;
                if (label.name == "PLAY" && parent != null && parent.name == "Options" &&
                    parent.parent != null && parent.parent.name == "MainMenu" &&
                    _raisedOptionsButtons.Add(parent.GetInstanceID()))
                    parent.anchoredPosition += new Vector2(0f, 34f);

            }

            foreach (var label in Resources.FindObjectsOfTypeAll<UnityEngine.UI.Text>())
            {
                if (label == null || !label.gameObject.scene.IsValid())
                    continue;
                string translated = catalog.Translate(label.text);
                if (!string.Equals(label.text, translated, StringComparison.Ordinal))
                    label.text = translated;
            }

            foreach (var label in Resources.FindObjectsOfTypeAll<TextMesh>())
            {
                if (label == null || !label.gameObject.scene.IsValid())
                    continue;
                string translated = catalog.Translate(label.text);
                if (!string.Equals(label.text, translated, StringComparison.Ordinal))
                    label.text = translated;
            }

            foreach (var dropdown in Resources.FindObjectsOfTypeAll<TMPro.TMP_Dropdown>())
            {
                if (dropdown == null || !dropdown.gameObject.scene.IsValid() || dropdown.options == null)
                    continue;

                bool changed = false;
                for (int i = 0; i < dropdown.options.Count; i++)
                {
                    TMPro.TMP_Dropdown.OptionData option = dropdown.options[i];
                    if (option == null)
                        continue;

                    string translated = catalog.Translate(option.text);
                    if (!string.Equals(option.text, translated, StringComparison.Ordinal))
                    {
                        option.text = translated;
                        changed = true;
                    }
                }

                if (changed)
                    dropdown.RefreshShownValue();
            }
        }

        private void LocalizeLogo(TMPro.TMP_Text label)
        {
            bool foreground = label.name == "BABDII";
            if (!foreground && label.name != "BackGround")
                return;

            var font = _fontFallbacks.MajorCyrillic;
            string localized = foreground ? "БаББдИ" : "БАББ\nДИ";
            if (font == null || (label.text != localized &&
                !string.Equals(label.text?.Trim(), "BABBDI", StringComparison.OrdinalIgnoreCase)))
                return;

            UseMajorCyrillic(label);
            label.enableWordWrapping = false;
            if (label.text != localized)
                label.text = localized;
        }

        private void UseMajorCyrillic(TMPro.TMP_Text label)
        {
            var font = _fontFallbacks.MajorCyrillic;
            if (font != null && label.font != font)
            {
                // Preserve the original material effects on the Cyrillic atlas.
                var material = TMPro.TMP_MaterialManager.GetFallbackMaterial(label.fontSharedMaterial, font.material);
                label.font = font;
                label.fontSharedMaterial = material;
            }
        }

        private void FitUiLabel(TMPro.TMP_Text label)
        {
            if (label == null || label.text == null)
                return;

            string text = label.text.Trim();
            if (label.name == "Informations" && text.StartsWith("СБРОСИТЬ ПРОГРЕСС", StringComparison.Ordinal))
            {
                label.horizontalAlignment = TMPro.HorizontalAlignmentOptions.Center;
                return;
            }

            float fitFactor = 0f;
            float availableWidth = label.rectTransform.rect.width;

            if (label.name == "BABDII" || label.name == "Volume(text)" ||
                string.Equals(text, "ЖУРНАЛ", StringComparison.OrdinalIgnoreCase) || text == "СОХРАНЕНИЕ...")
            {
                fitFactor = 0.97f;
                if (label.name == "Volume(text)" && label.transform.parent is RectTransform slider)
                    availableWidth = Mathf.Max(availableWidth, slider.rect.width);
            }
            else if (string.Equals(label.gameObject.name, "PLAY", StringComparison.Ordinal))
            {
                // Preserve vertical layout on Main Menu Options ("Настройки").
                if (string.Equals(text, "ИГРОАТЬ", StringComparison.Ordinal) ||
                    string.Equals(text, "ВЫЫЙ\nТИ", StringComparison.Ordinal) ||
                    string.Equals(text, "НАЗАД", StringComparison.Ordinal))
                {
                    fitFactor = 0.95f;
                }
            }
            else if (string.Equals(label.gameObject.name, "Text (TMP)", StringComparison.Ordinal) &&
                     label.transform.parent != null &&
                     PauseButtonParents.Contains(label.transform.parent.name) &&
                     PauseButtonTexts.Contains(text))
            {
                fitFactor = 0.90f;
                if (availableWidth <= 10f && label.transform.parent is RectTransform parentRect)
                    availableWidth = parentRect.rect.width;
            }

            if (fitFactor <= 0f || availableWidth <= 0f)
                return;

            int instanceId = label.GetInstanceID();
            if (_fittedTexts.TryGetValue(instanceId, out string lastText) &&
                string.Equals(lastText, text, StringComparison.Ordinal))
            {
                return;
            }

            if (!_baseFontSizes.TryGetValue(instanceId, out float baseSize))
            {
                baseSize = label.fontSize;
                _baseFontSizes[instanceId] = baseSize;
            }

            label.fontSize = baseSize;
            label.enableWordWrapping = false;
            label.ForceMeshUpdate();

            float requiredWidth = label.GetPreferredValues(label.text, Mathf.Infinity, Mathf.Infinity).x;
            if (label.name == "Volume(text)" && requiredWidth > label.rectTransform.rect.width)
            {
                RectTransform rect = label.rectTransform;
                float originalWidth = rect.rect.width;
                rect.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal,
                    Mathf.Min(availableWidth, requiredWidth / fitFactor));
                float shift = (rect.rect.width - originalWidth) * rect.pivot.x;
                rect.localPosition += rect.localRotation * new Vector3(shift * rect.localScale.x, 0f, 0f);
            }

            if (requiredWidth > availableWidth)
            {
                label.fontSize = baseSize * (availableWidth / requiredWidth) * fitFactor;
                label.ForceMeshUpdate();
            }

            _fittedTexts[instanceId] = text;
        }
    }
}
