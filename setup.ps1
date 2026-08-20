# Развёртывание монтажного цеха на новой машине.
#
# Репозиторий должен лежать в C:\Ferma\factory\reels-pro — пути к моделям,
# словарю и голосам в скриптах заданы от C:\Ferma. Другое место потребует
# правки путей в pipeline\*.py.
#
#   git clone https://github.com/Gor1x1/reels-pro C:\Ferma\factory\reels-pro
#   cd C:\Ferma\factory\reels-pro
#   .\setup.ps1
#
# Всё ставится без прав администратора. Скрипт можно гонять повторно —
# готовые шаги он пропускает.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$factory = Split-Path $root      # C:\Ferma\factory
$ferma = Split-Path $factory     # C:\Ferma

if ($root -ne "C:\Ferma\factory\reels-pro") {
    Write-Warning "репозиторий лежит в $root, а скрипты ждут C:\Ferma\factory\reels-pro"
    Write-Warning "либо перенеси папку, либо правь пути в pipeline\*.py"
}

function Step($name) { Write-Host "`n=== $name ===" -ForegroundColor Cyan }

# --- ffmpeg ---------------------------------------------------------------
Step "ffmpeg"
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ff) {
    winget install --id Gyan.FFmpeg --scope user --accept-package-agreements --accept-source-agreements
    Write-Host "ffmpeg поставлен — перезапусти терминал, чтобы PATH обновился, и прогони setup.ps1 ещё раз"
} else { Write-Host "есть: $($ff.Source)" }

# --- node -----------------------------------------------------------------
Step "node + зависимости движка"
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node -and (Test-Path "C:\Ferma\tools\node\node.exe")) {
    $env:PATH = "C:\Ferma\tools\node;" + $env:PATH
    $node = Get-Command node -ErrorAction SilentlyContinue
}
if (-not $node) {
    # MSI требует UAC, поэтому zip в пользовательскую папку
    Write-Host "качаю Node в C:\Ferma\tools\node (zip, без установщика)…"
    $nv = "v24.19.0"
    $zip = "$env:TEMP\node.zip"
    Invoke-WebRequest "https://nodejs.org/dist/$nv/node-$nv-win-x64.zip" -OutFile $zip
    Expand-Archive $zip "$env:TEMP\nodex" -Force
    New-Item -ItemType Directory -Force "C:\Ferma\tools" | Out-Null
    Move-Item "$env:TEMP\nodex\node-$nv-win-x64" "C:\Ferma\tools\node" -Force
    $env:PATH = "C:\Ferma\tools\node;" + $env:PATH
}
Push-Location $root
if (-not (Test-Path "$root\node_modules\remotion")) { npm install }
else { Write-Host "node_modules на месте" }
Pop-Location

# --- python ---------------------------------------------------------------
Step "python + библиотеки конвейера"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    winget install --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    Write-Host "python поставлен — перезапусти терминал и прогони setup.ps1 ещё раз"
    exit 0
}
# torch отдельно: обычный pip тянет CUDA-сборку на гигабайты, нужна CPU
python -m pip install --disable-pip-version-check --quiet torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install --disable-pip-version-check --quiet `
    faster-whisper piper-tts librosa soundfile numpy onnxruntime opencv-python pillow huggingface_hub

# --- модели ---------------------------------------------------------------
Step "модели (качаются один раз)"
$tts = "$factory\assets\tts"
$vc  = "$factory\assets\voiceclone"
New-Item -ItemType Directory -Force $tts, $vc, "$factory\config" | Out-Null

$dl = @"
from huggingface_hub import hf_hub_download
import shutil, pathlib
jobs = [
    ('davit312/piper-TTS-Armenian', 'v3/hy_AM-gor-medium.onnx',      r'$tts'),
    ('davit312/piper-TTS-Armenian', 'v3/hy_AM-gor-medium.onnx.json', r'$tts'),
    ('myshell-ai/OpenVoiceV2',      'converter/checkpoint.pth',      r'$vc'),
    ('myshell-ai/OpenVoiceV2',      'converter/config.json',         r'$vc'),
]
for repo, f, dst in jobs:
    out = pathlib.Path(dst) / pathlib.Path(f).name
    if out.exists():
        print('есть:', out.name); continue
    shutil.copy(hf_hub_download(repo, f), out)
    print('скачано:', out.name)
"@
python -c $dl

# конвертер тембра: берём только код, его TTS-часть не нужна
if (-not (Test-Path "C:\Ferma\tools\OpenVoice\openvoice")) {
    git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git "C:\Ferma\tools\OpenVoice"
} else { Write-Host "OpenVoice код на месте" }

# --- словарь распознавания -------------------------------------------------
Step "конфиг"
if (-not (Test-Path "$factory\config\fix-words.json")) {
    Copy-Item "$root\config\fix-words.json" "$factory\config\"
    Write-Host "fix-words.json разложен в factory\config"
} else { Write-Host "fix-words.json уже на месте" }

# --- проверка --------------------------------------------------------------
Step "проверка"
python -c "import faster_whisper, piper, librosa, soundfile, onnxruntime, cv2, torch; print('python-стек: ок')"
if (Test-Path "$tts\hy_AM-gor-medium.onnx") { Write-Host "синтез армянского: ок" }
if (Test-Path "$vc\checkpoint.pth") { Write-Host "клонирование голоса: ок" }

Write-Host @"

Готово. Чего скрипт НЕ делает:
  1. Голоса личностей (factory\personas\CP-0X) — личные данные, переносятся
     руками с основной машины, не через git.
  2. Банк роликов товара — тоже руками или по сети.
  3. Whisper качает свою модель (~460 МБ) при первом распознавании сам.

Проверить сборку: .\build.ps1 -Still -Frame 30
"@
