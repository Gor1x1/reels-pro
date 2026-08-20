# Сборка ролика одной командой.
#
# Обёртка нужна потому, что Remotion ищет public/ и точку входа относительно
# рабочего каталога, а вызовы из агента приходят из произвольной папки.
#
#   .\build.ps1                        собрать Reel в out/master.mp4
#   .\build.ps1 -Composition Caption-glow -Out out/demo.mp4
#   .\build.ps1 -Still -Frame 120      один кадр вместо всего ролика
#   .\build.ps1 -Master                плюс мастеринг звука и проверка

param(
    [string]$Composition = "Reel",
    [string]$Out = "out\master.mp4",
    [int]$Crf = 18,
    [switch]$Still,
    [int]$Frame = 0,
    [switch]$Master
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ffmpeg и node ставились в пользовательский профиль — в PATH процесса их может не быть
$ff = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin"
$env:PATH = "C:\Ferma\tools\node;$ff;$env:PATH"

$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$remotion = Join-Path $root "node_modules\.bin\remotion.cmd"

Push-Location $root
try {
    if ($Still) {
        $img = [System.IO.Path]::ChangeExtension($Out, ".png")
        & $remotion still $Composition $img --frame=$Frame --log=error
        if ($LASTEXITCODE -ne 0) { throw "кадр не собрался" }
        Write-Host "кадр: $img"
        return
    }

    $started = Get-Date
    & $remotion render $Composition $Out --crf=$Crf --log=error
    if ($LASTEXITCODE -ne 0) { throw "рендер упал" }
    $sec = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)

    $size = [math]::Round((Get-Item (Join-Path $root $Out)).Length / 1MB, 2)
    Write-Host "собрано за $sec сек, $size MB -> $Out"

    if ($Master) {
        $final = [System.IO.Path]::ChangeExtension($Out, ".final.mp4")
        & $py (Join-Path $root "pipeline\prep.py") master $Out --out $final
        & $py (Join-Path $root "pipeline\qc.py") $final
    }
}
finally {
    Pop-Location
}
