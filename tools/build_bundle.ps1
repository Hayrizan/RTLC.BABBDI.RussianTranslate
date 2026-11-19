param(
    [Parameter(Mandatory)][string]$UnityEditor,
    [Parameter(Mandatory)][string]$TextureSource
)
$ErrorActionPreference = 'Stop'
$UnityEditor = (Resolve-Path -LiteralPath $UnityEditor).Path
if ((Get-Item -LiteralPath $UnityEditor).VersionInfo.ProductVersion -notlike '2021.1.4f1*') {
    throw 'Use Unity 2021.1.4f1. BABBDI rejects the bundle built with Unity 2022.3.'
}
$root = Split-Path $PSScriptRoot -Parent
$project = Join-Path $root ('local_build/bundle_project_' + [Guid]::NewGuid().ToString('N'))
$inputDir = Join-Path $project 'Assets/RTLC'
$editorDir = Join-Path $project 'Assets/Editor'
New-Item -ItemType Directory -Force $inputDir,$editorDir,"$project/ProjectSettings","$project/Packages","$inputDir/Textures" | Out-Null
'{"dependencies":{}}' | Set-Content "$project/Packages/manifest.json"
Copy-Item "$PSScriptRoot/BundleEditor/BuildRtlc.cs" $editorDir
Copy-Item "$root/translations/translations.json" "$inputDir/translations.bytes"
foreach ($font in 'FuturaHandwritten-Cyrillic-Regular.ttf','MajorMonoDisplay-Cyrillic-Final-Regular.ttf') {
    Copy-Item "$root/assets/Fonts/$font" $inputDir
}
$m = Get-Content -LiteralPath "$TextureSource/texture_manifest.json" -Raw | ConvertFrom-Json
$index = 0
foreach ($entry in $m.textures) {
    $address = 'texture_{0:d3}.bytes' -f $index++
    Copy-Item -LiteralPath (Join-Path $TextureSource $entry.file) -Destination "$inputDir/Textures/$address"
    $entry.file = $address
}
$m | ConvertTo-Json -Depth 10 | Set-Content "$inputDir/texture_manifest.bytes" -Encoding utf8
$log = "$project/unity.log"
$p = Start-Process -FilePath $UnityEditor -ArgumentList '-batchmode','-nographics','-quit','-buildTarget','Win64','-projectPath',('"' + $project + '"'),'-executeMethod','BuildRtlc.Build','-logFile',('"' + $log + '"') -WindowStyle Hidden -Wait -PassThru
$expected = $index + 4
if ($p.ExitCode -ne 0 -or !(Select-String -LiteralPath $log -SimpleMatch "RTLC_BUNDLE_OK: $expected" -Quiet)) {
    Get-Content -LiteralPath $log -Tail 60
    throw "Unity AssetBundle build failed. See $log"
}
New-Item -ItemType Directory -Force "$root/build" | Out-Null
Copy-Item -LiteralPath "$project/BundleOutput/rtlc.bundle" -Destination "$root/build/rtlc.bundle" -Force
Write-Host "Built rtlc.bundle with $expected assets."
