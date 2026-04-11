# build_release.ps1 - Resona Desktop Pet release packager
# Usage: right-click -> Run with PowerShell
#        or: powershell -ExecutionPolicy Bypass -File build_release.ps1

$ErrorActionPreference = 'Continue'

$root    = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $root) { $root = $PWD.Path }
$stamp   = Get-Date -Format "yyyyMMdd_HHmm"
$staging = Join-Path $env:TEMP "Resona_Staging_$stamp"
$zipOut  = Join-Path $root "Resona_Desktop_Pet_$stamp.zip"

function Wait-Key { Read-Host "`nPress Enter to close" }

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Resona Desktop Pet - Release Builder"         -ForegroundColor Cyan
Write-Host "  Root  : $root"                                -ForegroundColor Gray
Write-Host "  Output: $zipOut"                              -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# robocopy helper - $StagingRoot passed explicitly to avoid scope issues
function Copy-Dir {
    param(
        [string]   $Src,
        [string]   $DstRel,
        [string]   $StagingRoot,
        [string[]] $ExcludeDirs  = @(),
        [string[]] $ExcludeFiles = @()
    )
    $dst = Join-Path $StagingRoot $DstRel
    New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
    $rc = @($Src, $dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP")
    $allXD = @("__pycache__") + $ExcludeDirs
    $allXF = @("*.pyc", "*.pyo") + $ExcludeFiles
    foreach ($d in $allXD) { $rc += "/XD"; $rc += $d }
    foreach ($f in $allXF) { $rc += "/XF"; $rc += $f }
    robocopy @rc | Out-Null
    Write-Host "  [+] $DstRel" -ForegroundColor Green
}

try {
    # --------------------------------------------------
    # Step 1/5 - Source code directories
    # --------------------------------------------------
    Write-Host "[Step 1/5] Copying source directories..." -ForegroundColor Cyan

    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
    New-Item -ItemType Directory -Path $staging | Out-Null

    Copy-Dir "$root\resona_desktop_pet" "resona_desktop_pet" $staging
    Copy-Dir "$root\mcpserver"          "mcpserver"          $staging -ExcludeFiles @("auto_keywords.json", "MCP_*.txt")
    Copy-Dir "$root\skills"             "skills"             $staging
    Copy-Dir "$root\tools"              "tools"              $staging
    Copy-Dir "$root\docs"               "docs"               $staging -ExcludeFiles @("QUICK_START.md", "QUICK_START_EN.md")

    # --------------------------------------------------
    # Step 2/5 - Resource packs
    #   setsuna: exclude models/ (distributed separately),
    #            memory files (personal data), state.json,
    #            private prompts, auto_keywords cache
    #   Resona_Default: downloaded by setup.ps1, not bundled
    # --------------------------------------------------
    Write-Host "[Step 2/5] Copying resource packs..." -ForegroundColor Cyan

    $setsunaExcludeFiles = @(
        "MEMORY.txt", "USER.txt", "state.json",
        "auto_keywords.json", "new_prompt.txt", "character_prompt.txt"
    )
    Copy-Dir "$root\packs\setsuna" "packs\setsuna" $staging `
        -ExcludeDirs $( @("models") ) `
        -ExcludeFiles $setsunaExcludeFiles

    # Safety net A: remove date-format memory logs (robocopy /XF has no regex support)
    $memDir = Join-Path $staging "packs\setsuna\memory"
    if (Test-Path $memDir) {
        $removed = Get-ChildItem $memDir -File |
            Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}\.txt$' } |
            ForEach-Object { Remove-Item $_.FullName -Force; $_.Name }
        if ($removed) {
            Write-Host "  [!] Removed memory logs: $($removed -join ', ')" -ForegroundColor Yellow
        }
    }

    # Safety net B: ensure models/ was not copied
    $stagingModels = Join-Path $staging "packs\setsuna\models"
    if (Test-Path $stagingModels) {
        Remove-Item $stagingModels -Recurse -Force
        Write-Host "  [!] Removed stray models directory" -ForegroundColor Yellow
    }

    # Write zeroed state.json
    # Use .NET writer to write BOM-free UTF-8 (PowerShell 5 Set-Content always adds BOM)
    [System.IO.File]::WriteAllText(
        (Join-Path $staging "packs\setsuna\state.json"),
        '{"total_clicks": 0}',
        [System.Text.UTF8Encoding]::new($false)
    )

    Copy-Dir "$root\packs\Example_Pack" "packs\Example_Pack" $staging

    # --------------------------------------------------
    # Step 3/5 - Root files
    # --------------------------------------------------
    Write-Host "[Step 3/5] Copying root files..." -ForegroundColor Cyan

    $rootFiles = @(
        "main.py", "run.bat", "setup.ps1", "setup_demo.ps1",
        "start_qq_bridge.bat", "tools_launcher.bat", "qq_bridge.py",
        "requirements.txt", "config.example.cfg",
        "README.md", "README_EN.md", "LICENSE", ".gitignore",
        "if_you_really_dont_know_what_is_python.ps1"
    )
    foreach ($f in $rootFiles) {
        $src = Join-Path $root $f
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $staging $f) -Force
            Write-Host "  [+] $f" -ForegroundColor Green
        } else {
            Write-Host "  [-] Not found (skipped): $f" -ForegroundColor DarkGray
        }
    }

    # --------------------------------------------------
    # Step 4/5 - Personal data scan (abort if found)
    # --------------------------------------------------
    Write-Host "[Step 4/5] Scanning for personal data..." -ForegroundColor Cyan

    $leakPatterns = @(
        @{ P = '^\d{4}-\d{2}-\d{2}\.txt$'; D = "memory log" },
        @{ P = '^MEMORY\.txt$';             D = "long-term memory" },
        @{ P = '^USER\.txt$';               D = "user profile" },
        @{ P = '^config\.cfg$';             D = "config (API keys)" },
        @{ P = '^auto_keywords\.json$';     D = "auto keywords cache" },
        @{ P = '\.ckpt$';                   D = "GPT voice model" },
        @{ P = '\.pth$';                    D = "SoVITS voice model" }
    )

    $leaks = @()
    Get-ChildItem $staging -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Replace($staging, '').TrimStart('\')
        foreach ($p in $leakPatterns) {
            if ($_.Name -match $p.P) {
                $leaks += "  [$($p.D)]  $rel"
            }
        }
    }

    if ($leaks.Count -gt 0) {
        Write-Host "  ABORT - sensitive files detected:" -ForegroundColor Red
        $leaks | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        Wait-Key
        exit 1
    }
    Write-Host "  OK - no sensitive files found" -ForegroundColor Green

    # --------------------------------------------------
    # Step 5/5 - Compress
    # --------------------------------------------------
    Write-Host "[Step 5/5] Compressing..." -ForegroundColor Cyan

    Compress-Archive -Path "$staging\*" -DestinationPath $zipOut -CompressionLevel Optimal
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }

    $sizeMB = [math]::Round((Get-Item $zipOut).Length / 1MB, 1)

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  Done! $zipOut ($sizeMB MB)"                    -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Distribute separately:" -ForegroundColor Yellow
    Write-Host "  - Voice models : setsuna_e8_s712.pth + setsuna-e15.ckpt" -ForegroundColor Yellow
    Write-Host "  - GPT-SoVITS   : ~7.7 GB (see README for download link)"  -ForegroundColor Yellow
    Write-Host "  - STT / Resona_Default : auto-downloaded by setup.ps1"   -ForegroundColor Yellow

} catch {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Red
    Write-Host "  Build FAILED"                                   -ForegroundColor Red
    Write-Host "  Error : $_"                                     -ForegroundColor Red
    Write-Host "  Line  : $($_.InvocationInfo.ScriptLineNumber)"  -ForegroundColor Red
    Write-Host "================================================" -ForegroundColor Red
    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
} finally {
    Wait-Key
}
