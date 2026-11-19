param(
    [string]$GameDir = $env:BABBDI_GAME_DIR,
    [string]$Configuration = 'Release',
    [string]$UnityEditor = $env:UNITY_EDITOR
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($GameDir)) {
    throw "Set BABBDI_GAME_DIR or pass -GameDir with the BABBDI installation directory."
}

$GameDir = (Resolve-Path -LiteralPath $GameDir).Path
$projectRoot = $PSScriptRoot
$projectFile = Join-Path $projectRoot 'src\BabbdiRussianTranslate\BabbdiRussianTranslate.csproj'
$textureSource = Join-Path $projectRoot 'local_build\BepInEx\plugins\RTLC.BABBDI.RussianTranslate\Textures'
$zipPath = Join-Path $projectRoot 'dist\BABBDI-Russian-0.1.0.zip'

if (-not (Test-Path -LiteralPath (Join-Path $textureSource 'texture_manifest.json'))) {
    throw "Texture overrides are missing. Run tools\build_texture_overrides.py first."
}

$env:BABBDI_GAME_DIR = $GameDir
dotnet build $projectFile -c $Configuration
if ($LASTEXITCODE -ne 0) {
    throw "dotnet build failed with exit code $LASTEXITCODE."
}

$pluginDll = Join-Path $projectRoot 'build\RTLC.BABBDI.RussianTranslate.dll'
if (-not (Test-Path -LiteralPath $pluginDll)) {
    throw "Build output not found: $pluginDll"
}

if ($UnityEditor) {
    & (Join-Path $projectRoot 'tools/build_bundle.ps1') -UnityEditor $UnityEditor -TextureSource $textureSource
}
$bundle = Join-Path $projectRoot 'build/rtlc.bundle'
if (!(Test-Path -LiteralPath $bundle -PathType Leaf)) {
    throw 'Build rtlc.bundle first or pass -UnityEditor.'
}

# Stage into a new directory so obsolete loose assets cannot enter the archive.
$stage = Join-Path $projectRoot ('local_build/package_' + [Guid]::NewGuid().ToString('N'))
$plugin = Join-Path $stage 'BepInEx/plugins/RTLC.BABBDI.RussianTranslate'
New-Item -ItemType Directory -Force -Path $plugin,(Split-Path $zipPath -Parent) | Out-Null
Copy-Item -LiteralPath $pluginDll,$bundle -Destination $plugin
Copy-Item -LiteralPath (Join-Path $projectRoot 'INSTALL.txt') -Destination $stage
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -Force
Write-Host "Created $zipPath"
