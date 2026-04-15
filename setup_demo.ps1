# Setsuna Desktop Pet - Demo Setup Script (No Voice Synthesis)
# Voice synthesis (SoVITS/STT) is disabled in this version.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$PYTHON_EMBED_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
$PIP_GET_URL = 'https://bootstrap.pypa.io/get-pip.py'
$PACK_URL = 'https://huggingface.co/datasets/JodieRuth/test1/resolve/main/Resona_Default.zip'
$FFMPEG_URL = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'

$DISCLAIMER = @'
*******************************************************************************
*                          SETSUNA DESKTOP PET - DEMO                          *
*******************************************************************************
* This is a demo build with voice synthesis (SoVITS/STT) disabled.           *
* Text chat, MCP tools, behavior triggers, and memory are fully functional.   *
*                                                                              *
* Licensed under CC BY-NC-SA 4.0.                                             *
* Assets contain third-party copyrighted materials (Navel / Okura Resona).   *
* For personal research and non-commercial use only.                          *
*******************************************************************************
'@

Clear-Host
Write-Host $DISCLAIMER -ForegroundColor Yellow

# --- 0. Mirror Setup ---
Write-Host "`n[Mirror] Enable mirror acceleration? (Highly recommended for Mainland China)" -ForegroundColor Cyan
Write-Host "  - HuggingFace -> hf-mirror.com (Models & Assets)"
Write-Host "  - GitHub      -> gh-proxy.com  (FFmpeg)"
Write-Host "  - PyPI        -> tsinghua.edu  (Python Dependencies)"
$useMirror = Read-Host 'Enable these mirrors? (Y/N, default is N)'
if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
    $PACK_URL = $PACK_URL -replace 'huggingface.co', 'hf-mirror.com'
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
    Write-Host "This is REQUIRED for PySide6 and NumPy to run."
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
    $proxyObject = New-Object System.Net.WebProxy($fullProxy)
    [System.Net.WebRequest]::DefaultWebProxy = $proxyObject
    Write-Host "[Resona] Proxy set to: $fullProxy"
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
    if (!(Test-Path 'runtime')) {
        New-Item -ItemType Directory -Path 'runtime'
        Write-Host '[Resona] Downloading Python 3.12 embedded version...'
        $curlPythonArgs = @("-L", "-f", $PYTHON_EMBED_URL, "-o", "python_embed.zip", "--retry", "5", "--connect-timeout", "30")
        if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlPythonArgs += @("-x", $fullProxy) }
        & curl.exe @curlPythonArgs

        Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime' -Force
        Remove-Item 'python_embed.zip'

        Write-Host '[Resona] Configuring pip...'
        $pthFile = Get-Item 'runtime\python312._pth'
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
    Write-Host '[Resona] Installing dependencies from requirements.txt...'
    $pipArgs = @("install", "-r", "requirements.txt", "--no-warn-script-location", "--upgrade", "--prefer-binary")

    if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
        $pipArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    }

    & $PYTHON_EXEC -m pip @pipArgs
}

# --- 4. User Choice Collection ---
Write-Host "`n[Resona] Download Preference Collection:" -ForegroundColor Cyan
$doDownloadPack = $false
$doDownloadFfmpeg = $false

Write-Host "[Demo] SoVITS voice synthesis: SKIPPED (not required for demo)" -ForegroundColor DarkGray
Write-Host "[Demo] STT speech recognition: SKIPPED (not required for demo)" -ForegroundColor DarkGray

if (!(Test-Path 'packs\Resona_Default\pack.json')) {
    $res = Read-Host 'Download Default Assets Pack (Resona_Default)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadPack = $true }
} else {
    Write-Host "[Resona] Default Pack detected. Skipping." -ForegroundColor Green
}

if (!(Test-Path 'ffmpeg\bin\ffmpeg.exe')) {
    $res = Read-Host 'Download FFmpeg (Required for audio playback)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadFfmpeg = $true }
} else {
    Write-Host "[Resona] FFmpeg detected. Skipping." -ForegroundColor Green
}

# --- 5. Sequential Execution of Downloads ---

# Assets Pack
if ($doDownloadPack) {
    Write-Host "`n[Resona] Starting Assets Pack download..." -ForegroundColor Cyan
    if (!(Test-Path 'packs')) { New-Item -ItemType Directory -Path 'packs' }

    $curlArgs = @("-L", "-f", "-C", "-", $PACK_URL, "-o", "pack.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlArgs += @("-x", $fullProxy) }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting Assets Pack...'
        Expand-Archive -Path 'pack.zip' -DestinationPath 'packs' -Force
        Remove-Item 'pack.zip'
    } else {
        Write-Error "[Resona] Assets Pack Download failed."
    }
}

# FFmpeg
if ($doDownloadFfmpeg) {
    Write-Host "`n[Resona] Starting FFmpeg download..." -ForegroundColor Cyan

    $curlArgs = @("-L", "-f", "-C", "-", $FFMPEG_URL, "-o", "ffmpeg.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlArgs += @("-x", $fullProxy) }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting FFmpeg...'
        Expand-Archive -Path 'ffmpeg.zip' -DestinationPath 'ffmpeg_temp' -Force
        Remove-Item 'ffmpeg.zip'

        $innerFolder = Get-ChildItem -Path 'ffmpeg_temp' -Directory | Select-Object -First 1
        if ($innerFolder) {
            if (Test-Path 'ffmpeg') { Remove-Item 'ffmpeg' -Recurse -Force }
            Move-Item -Path $innerFolder.FullName -Destination 'ffmpeg'
            Remove-Item 'ffmpeg_temp' -Recurse -Force
        }
    } else {
        Write-Error "[Resona] FFmpeg Download failed."
    }
}

# --- 6. API Key Configuration ---
Write-Host "`n[Config] Configure DeepSeek API Key" -ForegroundColor Cyan
Write-Host "  Get your key at: https://platform.deepseek.com/api_keys"
$apiKey = Read-Host 'Enter your DeepSeek API key (press Enter to skip and configure manually later)'

if ($apiKey -ne '') {
    $configPath = Join-Path $PSScriptRoot 'config.cfg'
    if (Test-Path $configPath) {
        $configContent = Get-Content $configPath -Raw

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

# --- 7. Disable SoVITS in config.cfg ---
Write-Host "`n[Demo] Disabling SoVITS voice synthesis in config.cfg..." -ForegroundColor Cyan
$configPath = Join-Path $PSScriptRoot 'config.cfg'
if (Test-Path $configPath) {
    $configContent = Get-Content $configPath -Raw

    # Find [SoVITS] section and set enabled = false
    $configContent = [regex]::Replace(
        $configContent,
        '(\[SoVITS\][^\[]*?enabled\s*=\s*)true',
        '${1}false',
        [System.Text.RegularExpressions.RegexOptions]::Singleline
    )

    Set-Content -Path $configPath -Value $configContent -NoNewline
    Write-Host "[Demo] SoVITS disabled. The pet will run in text-only mode." -ForegroundColor Green
} else {
    Write-Host "[Warning] config.cfg not found. Please manually set 'enabled = false' under [SoVITS]." -ForegroundColor Yellow
}

Write-Host "`n[Resona] Demo setup complete!" -ForegroundColor Green
Write-Host "  - Run run.bat to start the pet." -ForegroundColor White
Write-Host "  - The pet will respond in text (no voice output)." -ForegroundColor White
Write-Host "  - MCP tools, memory, and behavior triggers are fully enabled." -ForegroundColor White
pause
