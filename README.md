# Русификатор BABBDI

Русский интерфейс, диалоги и имена персонажей, 41 текстурная замена, две объёмные вывески и кириллические шрифты. В настройках добавлен переключатель полноэкранного режима.

## Установка

1. Закройте BABBDI. Если раньше устанавливали этот русификатор, переместите его старую папку из `BepInEx/plugins`.
2. Скачайте `RTLC.BABBDI.RussianTranslate.zip` из раздела Releases и распакуйте рядом с `Babbdi.exe`.
3. Запустите игру. Журнал загрузки находится в `BepInEx/LogOutput.log`.

Готовый ZIP рассчитан на BABBDI для Windows x64 (Unity Mono) и включает BepInEx 5.4.23.6. В папке `BepInEx/plugins/RTLC.BABBDI.RussianTranslate` находятся DLL плагина и `rtlc.bundle`.

## Сборка

Понадобятся установленная BABBDI, .NET SDK и Unity 2021.1.4f1 для пересборки бандла. Укажите путь к игре переменной `BABBDI_GAME_DIR`.

```powershell
dotnet build .\src\BabbdiRussianTranslate\BabbdiRussianTranslate.csproj -c Release
```

Чтобы пересобрать бандл с утверждённым набором текстур, поместите PNG и `texture_manifest.json` в `local_build/BepInEx/plugins/RTLC.BABBDI.RussianTranslate/Textures`. Затем запустите:

```powershell
.\build_release.ps1 -GameDir $env:BABBDI_GAME_DIR -UnityEditor '<путь к Unity.exe версии 2021.1.4f1>'
```

Скрипт создаёт архив плагина без загрузчика. Для обычной установки используйте готовый архив из релиза. `Assets.zip` — отдельный архив ресурсов, для установки русификатора он не нужен.
