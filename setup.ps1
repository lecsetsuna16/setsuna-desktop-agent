# Setsuna Desktop Pet Ultimate Setup Script
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$PYTHON_EMBED_URL = 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip'
$PIP_GET_URL = 'https://bootstrap.pypa.io/get-pip.py'
$SOVITS_URL = 'https://huggingface.co/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604.zip'
$PACK_URL = 'https://huggingface.co/datasets/JodieRuth/test1/resolve/main/Resona_Default.zip'
# External Dependency: SenseVoiceSmall (by Alibaba FunASR)
# Distribution & Conversion by k2-fsa/sherpa-onnx (Apache-2.0)
$STT_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2'
$FFMPEG_URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'

# --- GPU Detection ---
$gpus = Get-CimInstance Win32_VideoController
$isNvidia50 = $false
foreach ($gpu in $gpus) {
    $gpuName = $gpu.Name.ToUpper()
    if ($gpuName -like "*NVIDIA*" -and $gpuName -like "*RTX 50*") {
        $isNvidia50 = $true
        $SOVITS_URL = 'https://huggingface.co/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.zip'
        Write-Host "[Resona] Detected NVIDIA 50-series GPU: $($gpu.Name). Using optimized SoVITS version." -ForegroundColor Green
        break
    }
}

$DISCLAIMER = @'
*******************************************************************************
*                                DISCLAIMER                                   *
*******************************************************************************
* This code is licensed under CC BY-NC-SA 4.0.                                *
* The assets downloaded by this script contain third-party copyrighted        *
* materials from Navel (Omega Vision, Inc.).                                  *
* 1. Assets are for personal research and non-commercial use only.            *
* 2. Commercial use of assets or models is strictly prohibited.               *
* 3. This script is a tool only and does not own or distribute the assets.    *
*******************************************************************************
'@

Clear-Host
Write-Host $DISCLAIMER -ForegroundColor Yellow

# --- Pre-flight: Project path non-ASCII check ---
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($scriptDir -match '[^\x00-\x7F]') {
    Write-Host "[Error] Project path contains non-ASCII characters:" -ForegroundColor Red
    Write-Host "  $scriptDir" -ForegroundColor Red
    Write-Host "  Resona WILL crash at runtime. Please move the project folder to a path" -ForegroundColor Red
    Write-Host "  that contains only English letters, numbers, and hyphens/underscores." -ForegroundColor Red
    pause
    exit 1
}

# --- 0. Mirror Setup ---
Write-Host "`n[Mirror] Enable mirror acceleration? (Highly recommended for Mainland China)" -ForegroundColor Cyan
Write-Host "  - HuggingFace -> hf-mirror.com (Models & Assets)"
Write-Host "  - GitHub      -> gh-proxy.com  (STT Models)"
Write-Host "  - PyPI        -> tsinghua.edu  (Python Dependencies)"
$useMirror = Read-Host 'Enable these mirrors? (Y/N, default is N)'
if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
    $SOVITS_URL = $SOVITS_URL -replace 'huggingface.co', 'hf-mirror.com'
    $PACK_URL = $PACK_URL -replace 'huggingface.co', 'hf-mirror.com'
    # GitHub Mirror
    $STT_URL = "https://gh-proxy.com/" + $STT_URL
    $FFMPEG_URL = "https://gh-proxy.com/" + $FFMPEG_URL
    Write-Host "[Resona] Using Mirrors: hf-mirror.com & gh-proxy.com" -ForegroundColor Cyan
}

# --- 0.1 C++ Runtime Check ---
Write-Host "`n[Check] Checking for Microsoft Visual C++ Redistributable..." -ForegroundColor Cyan
$vc_installed = $false
$vc_registry_paths = @(
    "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
)

foreach ($path in $vc_registry_paths) {
    if (Test-Path $path) {
        $vc_installed = $true
        break
    }
}

if (-not $vc_installed) {
    Write-Host "[Warning] Microsoft Visual C++ Redistributable (2015-2022) not detected!" -ForegroundColor Yellow
    Write-Host "This is REQUIRED for PySide6, NumPy, and SoVITS to run."
    Write-Host "Download link: https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $installVC = Read-Host 'Would you like to open the download page? (Y/N, default is Y)'
    if ($installVC -ne 'N' -and $installVC -ne 'n') {
        Start-Process "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Host "Please install the redistributable and then restart this script." -ForegroundColor Yellow
        pause
    }
} else {
    Write-Host "[Resona] C++ Runtime detected." -ForegroundColor Green
}

# --- 1. Proxy Setup ---
$useProxy = Read-Host 'Do you need a proxy for downloading? (Y/N, default is N)'
$proxyObject = $null
if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
    $proxyAddr = Read-Host 'Enter proxy address (e.g., 127.0.0.1)'
    $proxyPort = Read-Host 'Enter proxy port (e.g., 7890)'
    $fullProxy = "http://$($proxyAddr):$proxyPort"
    $env:HTTP_PROXY = $fullProxy
    $env:HTTPS_PROXY = $fullProxy
    
    # Configure PowerShell session to use this proxy for all web requests
    $proxyObject = New-Object System.Net.WebProxy($fullProxy)
    [System.Net.WebRequest]::DefaultWebProxy = $proxyObject
    Write-Host "[Resona] Proxy set to: $fullProxy"
}

# --- 1.5. Python Version Check ---
Write-Host "`n[Check] Checking system Python version..." -ForegroundColor Cyan
$pyVersionOk = $false
try {
    $pyVerStr = & python --version 2>&1
    if ($pyVerStr -match 'Python (\d+)\.(\d+)') {
        $pyMajor = [int]$Matches[1]
        $pyMinor = [int]$Matches[2]
        if ($pyMajor -eq 3 -and $pyMinor -ge 10 -and $pyMinor -le 13) {
            $pyVersionOk = $true
            Write-Host "[Check] Python $pyMajor.$pyMinor detected. Compatible." -ForegroundColor Green
        } else {
            Write-Host "[Warning] Python $pyMajor.$pyMinor detected. Resona requires Python 3.10 - 3.13." -ForegroundColor Yellow
            Write-Host "          Python 3.14+ is NOT supported due to dependency limitations." -ForegroundColor Yellow
            Write-Host "          Recommended: install Python 3.10 from https://python.org" -ForegroundColor Yellow
            Write-Host "          Alternatively, select Mode 3 below to use a bundled Python 3.10." -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "[Check] Could not detect system Python. Select Mode 3 if Python is not installed." -ForegroundColor Yellow
}

# --- 2. Installation Mode ---
Write-Host "`n[Resona] Select Environment Installation Mode:" -ForegroundColor Cyan
Write-Host '1. Global Installation (Install to system Python)'
Write-Host '2. Virtual Environment (Create venv in project folder, RECOMMENDED)'
Write-Host '3. Full Runtime (Download portable Python 3.12, for users without Python)'
Write-Host '4. Skip Environment Deployment (Resource download only)'
$mode = Read-Host 'Enter number (1/2/3/4)'

$PYTHON_EXEC = 'python'
$skipInstall = $false

if ($mode -eq '3') {
    if (!(Test-Path 'runtime\python.exe')) {
        if (!(Test-Path 'runtime')) { New-Item -ItemType Directory -Path 'runtime' }

        Write-Host '[Resona] Downloading Python 3.12 embedded version...'
        $curlPythonArgs = @("-L", "-f", $PYTHON_EMBED_URL, "-o", "python_embed.zip", "--retry", "5", "--connect-timeout", "30")
        if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlPythonArgs += @("-x", $fullProxy) }
        & curl.exe @curlPythonArgs
        
        Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime' -Force
        Remove-Item 'python_embed.zip'

        Write-Host '[Resona] Configuring pip...'
        $pthFile = Get-Item 'runtime\python310._pth'
        (Get-Content $pthFile) -replace '#import site', 'import site' | Set-Content $pthFile
        
        $curlPipArgs = @("-L", "-f", $PIP_GET_URL, "-o", "runtime\get-pip.py", "--retry", "5", "--connect-timeout", "30")
        if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlPipArgs += @("-x", $fullProxy) }
        & curl.exe @curlPipArgs
        
        $getPipArgs = @("runtime\get-pip.py", "--no-warn-script-location")
        if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
            $getPipArgs += @("--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple")
        }
        .\runtime\python.exe @getPipArgs
        Remove-Item 'runtime\get-pip.py'
        

        Write-Host '[Resona] Pre-installing build tools (setuptools, wheel)...'
        $preInstallArgs = @("install", "setuptools", "wheel", "--no-warn-script-location", "--prefer-binary")
        if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
            $preInstallArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
        }
        .\runtime\python.exe -m pip @preInstallArgs
    }
    $PYTHON_EXEC = '.\runtime\python.exe'
}
elseif ($mode -eq '2') {
    # Verify system Python is a compatible version before creating venv
    $venvPyOk = $false
    try {
        $venvVerStr = & python --version 2>&1
        if ($venvVerStr -match 'Python (\d+)\.(\d+)') {
            $vMajor = [int]$Matches[1]; $vMinor = [int]$Matches[2]
            if ($vMajor -eq 3 -and $vMinor -ge 10 -and $vMinor -le 13) { $venvPyOk = $true }
        }
    } catch {}
    if (-not $venvPyOk) {
        Write-Host "[Error] System Python is not 3.10-3.13. Cannot create a working venv." -ForegroundColor Red
        Write-Host "        Install Python 3.10 from https://python.org, or choose Mode 3 instead." -ForegroundColor Yellow
        pause; exit 1
    }
    Write-Host '[Resona] Creating virtual environment (venv)...'
    python -m venv venv
    $PYTHON_EXEC = '.\venv\Scripts\python.exe'
}
elseif ($mode -eq '4') {
    Write-Host '[Resona] Skipping environment deployment.'
    $skipInstall = $true
}
else {
    Write-Host '[Resona] Using system Python.'
    $PYTHON_EXEC = 'python'
}

# --- 3. Requirements ---
if (-not $skipInstall) {
    Write-Host '[Resona] Pre-installing numpy (binary only, avoids compilation errors)...'
    $numpyArgs = @("install", "numpy>=1.26.0,<2.0.0", "--only-binary", ":all:", "--no-warn-script-location")
    if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
        $numpyArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    }
    & $PYTHON_EXEC -m pip @numpyArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[Warning] numpy pre-install failed for this Python version." -ForegroundColor Yellow
        Write-Host "          Ensure you are using Python 3.10 - 3.13, or switch to Mode 3." -ForegroundColor Yellow
    }

    Write-Host '[Resona] Installing dependencies from requirements.txt...'
    $pipArgs = @("install", "-r", "requirements.txt", "--no-warn-script-location", "--upgrade", "--prefer-binary")

    if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
        $pipArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    }

    & $PYTHON_EXEC -m pip @pipArgs
}

# --- 4. User Choice Collection ---
Write-Host "`n[Resona] Download Preference Collection:" -ForegroundColor Cyan
$doDownloadSovits = $false
$doDownloadPack = $false
$doDownloadStt = $false
$doDownloadFfmpeg = $false

if (!(Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604\api_v2.py')) {
    $res = Read-Host 'Download SoVITS Inference Engine (~7.7GB Zip / 10.5GB Unpacked)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadSovits = $true }
} else {
    Write-Host "[Resona] SoVITS detected. Skipping." -ForegroundColor Green
}

if (!(Test-Path 'packs\Resona_Default\pack.json')) {
    $res = Read-Host 'Download Default Assets Pack (Resona_Default)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadPack = $true }
} else {
    Write-Host "[Resona] Default Pack detected. Skipping." -ForegroundColor Green
}

if (!(Test-Path 'models\stt\sensevoice\model.int8.onnx') -and !(Test-Path 'models\stt\sensevoice\zh.onnx')) {
    # Check for any .onnx file just in case
    $hasOnnx = Get-ChildItem -Path 'models\stt\sensevoice' -Filter *.onnx -Recurse -ErrorAction SilentlyContinue
    if (!$hasOnnx) {
        $res = Read-Host 'Download STT (SenseVoice) Model (3GB Unpacked)? (Y/N)'
        if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadStt = $true }
    } else {
        Write-Host "[Resona] STT Model detected. Skipping." -ForegroundColor Green
    }
} else {
    Write-Host "[Resona] STT Model detected. Skipping." -ForegroundColor Green
}

if (!(Test-Path 'ffmpeg\bin\ffmpeg.exe')) {
    $res = Read-Host 'Download FFmpeg (Required for audio processing)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadFfmpeg = $true }
} else {
    Write-Host "[Resona] FFmpeg detected. Skipping." -ForegroundColor Green
}

# --- 5. Sequential Execution of Downloads ---

# SoVITS
if ($doDownloadSovits) {
    Write-Host "`n[Resona] Starting SoVITS download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching SoVITS archive using curl (more reliable for large files)...'
    if (!(Test-Path 'GPT-SoVITS')) { New-Item -ItemType Directory -Path 'GPT-SoVITS' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $SOVITS_URL, "-o", "sovits.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }
    
    Write-Host "[Resona] Running: curl.exe ..." -ForegroundColor Gray
    & curl.exe @curlArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting SoVITS (this may take a while)...'
        Expand-Archive -Path 'sovits.zip' -DestinationPath 'GPT-SoVITS' -Force
        Remove-Item 'sovits.zip'

        # Handle 50-series folder renaming
        if (Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50') {
            Write-Host '[Resona] Renaming optimized SoVITS folder...'
            Rename-Item -Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50' -NewName 'GPT-SoVITS-v2pro-20250604'
        }
    } else {
        Write-Host "[Warning] SoVITS download failed (curl exit $LASTEXITCODE). You can re-run setup or download manually." -ForegroundColor Yellow
    }
}

# Assets Pack
if ($doDownloadPack) {
    Write-Host "`n[Resona] Starting Assets Pack download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching Assets Pack using curl...'
    if (!(Test-Path 'packs')) { New-Item -ItemType Directory -Path 'packs' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $PACK_URL, "-o", "pack.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting Assets Pack...'
        Expand-Archive -Path 'pack.zip' -DestinationPath 'packs' -Force
        Remove-Item 'pack.zip'
    } else {
        Write-Host "[Warning] Assets Pack download failed (curl exit $LASTEXITCODE). You can re-run setup or download manually." -ForegroundColor Yellow
    }
}

# STT Model
if ($doDownloadStt) {
    Write-Host "`n[Resona] Starting STT Model download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching STT Model...'
    if (!(Test-Path 'models\stt')) { New-Item -ItemType Directory -Path 'models\stt' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $STT_URL, "-o", "stt_model.tar.bz2", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting STT Model (this may take a while)...'
        if (!(Test-Path 'models\stt\sensevoice')) { New-Item -ItemType Directory -Path 'models\stt\sensevoice' }
        & tar.exe -xvf stt_model.tar.bz2 -C models\stt\sensevoice --strip-components 1
        Remove-Item 'stt_model.tar.bz2'
    } else {
        Write-Host "[Warning] STT Model download failed (curl exit $LASTEXITCODE). You can re-run setup or download manually." -ForegroundColor Yellow
    }
}

# FFmpeg
if ($doDownloadFfmpeg) {
    Write-Host "`n[Resona] Starting FFmpeg download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching FFmpeg...'
    
    $curlArgs = @("-L", "-f", "-C", "-", $FFMPEG_URL, "-o", "ffmpeg.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        try {
            Write-Host '[Resona] Extracting FFmpeg...'
            Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'ffmpeg_temp' -Force
            Remove-Item 'ffmpeg.zip' -ErrorAction SilentlyContinue

            # Move the inner folder to 'ffmpeg'
            $innerFolder = Get-ChildItem -Path 'ffmpeg_temp' -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($innerFolder) {
                if (Test-Path 'ffmpeg') { Remove-Item 'ffmpeg' -Recurse -Force }
                Move-Item -Path $innerFolder.FullName -Destination 'ffmpeg'
                Remove-Item 'ffmpeg_temp' -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host '[Resona] FFmpeg installed.' -ForegroundColor Green
            } else {
                Write-Host "[Warning] FFmpeg archive extracted but no folder found inside. Check ffmpeg_temp\." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "[Warning] FFmpeg extraction failed: $_" -ForegroundColor Yellow
            Write-Host "          You can install FFmpeg manually: place ffmpeg.exe in ffmpeg\bin\" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[Warning] FFmpeg download failed (curl exit $LASTEXITCODE). You can re-run setup or download manually." -ForegroundColor Yellow
        Write-Host "          Manual download: https://github.com/BtbN/FFmpeg-Builds/releases" -ForegroundColor Yellow
        if (Test-Path 'ffmpeg.zip') { Remove-Item 'ffmpeg.zip' -ErrorAction SilentlyContinue }
    }
}

# --- 6. Ensure config.cfg exists ---
$configPath = Join-Path $PSScriptRoot 'config.cfg'
$examplePath = Join-Path $PSScriptRoot 'config.example.cfg'
if (!(Test-Path $configPath)) {
    if (Test-Path $examplePath) {
        Copy-Item -Path $examplePath -Destination $configPath
        Write-Host "[Config] config.cfg not found. Created from config.example.cfg." -ForegroundColor Cyan
    } else {
        Write-Host "[Warning] Neither config.cfg nor config.example.cfg found. Please create config.cfg manually." -ForegroundColor Yellow
    }
}

Write-Host "`n[Config] Configure DeepSeek API Key" -ForegroundColor Cyan
Write-Host "  Get your key at: https://platform.deepseek.com/api_keys"
$apiKey = Read-Host 'Enter your DeepSeek API key (press Enter to skip and configure manually later)'

if ($apiKey -ne '') {
    $configPath = Join-Path $PSScriptRoot 'config.cfg'
    if (Test-Path $configPath) {
        $configContent = Get-Content $configPath -Raw

        # Replace the DeepSeek section api_key (identified by proximity to deepseek.com base_url)
        # Strategy: find the block with base_url = https://api.deepseek.com and set its api_key
        $configContent = $configContent -replace `
            '(base_url\s*=\s*https://api\.deepseek\.com[\r\n]+model_name\s*=\s*deepseek-reasoner[\r\n]+chat_model_name\s*=\s*deepseek-chat)', `
            "base_url = https://api.deepseek.com`r`nmodel_name = deepseek-reasoner`r`nchat_model_name = deepseek-chat"

        # Simpler targeted replace: find api_key line just before base_url = https://api.deepseek.com
        $configContent = [regex]::Replace(
            $configContent,
            '(api_key\s*=\s*)[^\r\n]*(\r?\n(?:[^\r\n]*\r?\n){0,2}base_url\s*=\s*https://api\.deepseek\.com)',
            "`${1}$apiKey`$2"
        )

        Set-Content -Path $configPath -Value $configContent -NoNewline
        Write-Host "[Config] DeepSeek API key written to config.cfg." -ForegroundColor Green
    } else {
        Write-Host "[Warning] config.cfg not found. Please set your API key manually." -ForegroundColor Yellow
    }
} else {
    Write-Host "[Config] Skipped. Remember to set api_key under [DeepSeek] in config.cfg before running." -ForegroundColor Yellow
}

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host " Setup Complete!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Next steps:" -ForegroundColor White
Write-Host "  1. Open config.cfg with VS Code or Notepad++" -ForegroundColor White
Write-Host "     !! Do NOT use Windows Notepad - it will corrupt the" -ForegroundColor Yellow
Write-Host "     !! encoding and cause crashes on startup." -ForegroundColor Yellow
Write-Host "  2. Set 'model_select' to your provider (2 = DeepSeek recommended)" -ForegroundColor White
Write-Host "  3. Fill in the api_key for your chosen model section" -ForegroundColor White
Write-Host "  4. Double-click run.bat to start" -ForegroundColor White
Write-Host ""
Write-Host " model_select reference:" -ForegroundColor Cyan
Write-Host "   1=OpenAI  2=DeepSeek  3=Claude  4=Kimi  5=Gemini" -ForegroundColor Gray
Write-Host "   6=Grok    7=Qwen      8=GitHub  9=Compatible  10=Zhipu  11=Local" -ForegroundColor Gray
Write-Host ""
Write-Host " Note: SoVITS voice engine takes 50-90s to load on first start." -ForegroundColor White
Write-Host " A blank window during this time is normal." -ForegroundColor White
Write-Host "========================================================" -ForegroundColor Cyan
pause
