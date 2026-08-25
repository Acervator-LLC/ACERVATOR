# Acervator - Windows Build
# Output: dist\Acervator\Acervator.exe

Set-Location $PSScriptRoot

# Read the live version from src/__init__.py so the banner is never stale
# (v3.15.98 fix — was hardcoded "v3.7.0" causing operator confusion when
# building newer source).
$versionStr = "unknown"
try {
    $initText = Get-Content -Path "src\__init__.py" -Raw -ErrorAction Stop
    if ($initText -match '__version__\s*=\s*"([0-9.]+)"') {
        $versionStr = $Matches[1]
    }
} catch {
    # Fall through with "unknown"
}

Write-Host ""
Write-Host "  Acervator v$versionStr" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Strip Mark of the Web from ALL files ---
Write-Host "  Stripping download security flags..." -ForegroundColor Gray
Get-ChildItem -Path . -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

# --- Step 2: Install dependencies ---
#
# Issue #94 - this line used to hand-copy 14 package names. It named
# `requests`, which no file in the repository imports, and it did NOT
# name `defusedxml`, which src\gui\crypto_news_ticker.py imports at
# module level. The names now come from pyproject.toml, which is the one
# source. `tools/deps.py build` answers the core set plus the `build` and
# `report` extras, which is what a PyInstaller HOST needs.
$deps = & python -m tools.deps requirements build
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: could not read the dependency set from pyproject.toml" -ForegroundColor Red
    exit 1
}
if (-not $deps) {
    Write-Host "  ERROR: empty dependency set; refusing to build" -ForegroundColor Red
    exit 1
}
pip install @deps --quiet --upgrade

# --- Step 3: Clean caches ---
Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# --- Step 4: Build ---
pyinstaller Acervator_win.spec --noconfirm

# --- Step 5: Strip MOTW from built exe and all dist files ---
if (Test-Path ".\dist") {
    Get-ChildItem -Path ".\dist" -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
}

# --- Step 6: Add Defender exclusion for the output folder ---
$distPath = Join-Path $PSScriptRoot "dist\Acervator"
try {
    Add-MpPreference -ExclusionPath $distPath -ErrorAction Stop
    Write-Host "  Defender exclusion added: $distPath" -ForegroundColor Green
} catch {
    Write-Host "  Note: Run as Administrator to add Defender exclusion" -ForegroundColor Yellow
    Write-Host "  Or manually add this folder to Defender exclusions:" -ForegroundColor Yellow
    Write-Host "    $distPath" -ForegroundColor White
}

Write-Host ""
if (Test-Path ".\dist\Acervator\Acervator.exe") {
    Write-Host "  DONE: $distPath\Acervator.exe" -ForegroundColor Green
} else {
    Write-Host "  exe not at expected path. Searching..." -ForegroundColor Yellow
    Get-ChildItem -Path . -Recurse -Filter "Acervator.exe" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  Found: $($_.FullName)" -ForegroundColor Green }
}
Write-Host ""
