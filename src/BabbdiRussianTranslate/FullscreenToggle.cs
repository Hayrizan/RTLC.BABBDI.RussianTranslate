using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RTLC.BABBDI.RussianTranslate
{
    internal sealed class FullscreenToggle : MonoBehaviour
    {
        private const string RowName = "RTLC Fullscreen";
        private const string Preference = "RTLC.BABBDI.Fullscreen";
        private Toggle _toggle;

        public static void Install()
        {
            ApplyPreference();
            foreach (var template in Resources.FindObjectsOfTypeAll<Toggle>())
            {
                if (template == null || !template.gameObject.scene.IsValid() ||
                    !(template.transform is RectTransform source) || source.parent == null ||
                    source.parent.name != "Options" || source.parent.Find(RowName) != null)
                    continue;

                var tmp = template.GetComponentInChildren<TMP_Text>(true);
                var legacy = template.GetComponentInChildren<Text>(true);
                string text = (tmp != null ? tmp.text : legacy?.text)?.Trim();
                bool mainMenu = source.parent.parent != null && source.parent.parent.name == "OptionsMenu";
                string expected = mainMenu ? "РЕЖИМ СПИДРАНА" : "ИНВЕРСИЯ X";
                if (!string.Equals(text, expected, StringComparison.OrdinalIgnoreCase))
                    continue;

                if (!(template.targetGraphic is Image background) || !(template.graphic is Image check))
                    continue;

                var row = new GameObject(RowName, typeof(RectTransform));
                row.SetActive(false);
                var rect = (RectTransform)row.transform;
                CopyRect(source, rect, source.parent);
                var toggle = row.AddComponent<Toggle>();
                var box = CopyImage(background, rect);
                toggle.targetGraphic = box;
                toggle.graphic = CopyImage(check, box.rectTransform);
                toggle.colors = template.colors;
                toggle.toggleTransition = template.toggleTransition;

                var captionObject = new GameObject("Label", typeof(RectTransform));
                CopyRect(tmp != null ? tmp.rectTransform : legacy.rectTransform,
                    (RectTransform)captionObject.transform, rect);
                if (tmp != null)
                {
                    var caption = captionObject.AddComponent<TextMeshProUGUI>();
                    caption.font = tmp.font;
                    caption.fontSharedMaterial = tmp.fontSharedMaterial;
                    caption.fontSize = tmp.fontSize;
                    caption.alignment = tmp.alignment;
                    caption.color = tmp.color;
                    caption.text = "ПОЛНЫЙ ЭКРАН";
                }
                else
                {
                    var caption = captionObject.AddComponent<Text>();
                    caption.font = legacy.font;
                    caption.fontSize = legacy.fontSize;
                    caption.alignment = legacy.alignment;
                    caption.color = legacy.color;
                    caption.horizontalOverflow = HorizontalWrapMode.Overflow;
                    caption.text = "ПОЛНЫЙ ЭКРАН";
                }

                if (mainMenu)
                {
                    source.anchoredPosition -= new Vector2(155f, 0f);
                    rect.anchoredPosition += new Vector2(155f, 0f);
                }
                else
                {
                    rect.anchoredPosition += new Vector2(source.rect.width + 12f, 0f);
                }

                row.AddComponent<FullscreenToggle>()._toggle = toggle;
                toggle.onValueChanged.AddListener(value =>
                {
                    PlayerPrefs.SetInt(Preference, value ? 1 : 0);
                    PlayerPrefs.Save();
                    ApplyPreference();
                });
                row.SetActive(true);
            }
        }

        private static void CopyRect(RectTransform source, RectTransform target, Transform parent)
        {
            target.SetParent(parent, false);
            target.anchorMin = source.anchorMin;
            target.anchorMax = source.anchorMax;
            target.pivot = source.pivot;
            target.sizeDelta = source.sizeDelta;
            target.anchoredPosition = source.anchoredPosition;
            target.localScale = source.localScale;
        }

        private static Image CopyImage(Image source, RectTransform parent)
        {
            var image = new GameObject(source.name, typeof(RectTransform), typeof(Image)).GetComponent<Image>();
            CopyRect(source.rectTransform, image.rectTransform, parent);
            image.sprite = source.sprite;
            image.type = source.type;
            image.color = source.color;
            image.raycastTarget = source.raycastTarget;
            return image;
        }

        private static void ApplyPreference()
        {
            if (!PlayerPrefs.HasKey(Preference))
                return;

            var mode = PlayerPrefs.GetInt(Preference) != 0
                ? FullScreenMode.FullScreenWindow : FullScreenMode.Windowed;
            if (Screen.fullScreenMode != mode)
                Screen.fullScreenMode = mode;
        }

        private void OnEnable()
        {
            ApplyPreference();
            _toggle.SetIsOnWithoutNotify(PlayerPrefs.GetInt(Preference, Screen.fullScreen ? 1 : 0) != 0);
        }
    }
}