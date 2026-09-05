# Acervator - Windows Build
# Output: dist\Acervator-<version>-<variant>\Acervator-<version>-<variant>.exe
#
# Builds one executable per variant. Nothing in dist is deleted or
# overwritten: the spec claims a name that is not taken, so every build
# stays runnable beside the ones before it.

param(
    [string]$Variant = ""
)

Set-Location $PSScriptRoot

# The environment variable the spec reads and the variant names are declared in
# src/_variant.py. Asking for them keeps no second copy here.
$variantEnvVar = & python -m tools.build_variants env-var
if ($LASTEXITCODE -ne 0 -or -not $variantEnvVar) {
    Write-Host "  ERROR: could not read the build-variant environment variable" -ForegroundColor Red
    exit 1
}
$variantEnvVar = ([string]($variantEnvVar | Select-Object -First 1)).Trim()

if ($Variant) {
    $requested = & python -m tools.build_variants select --variant $Variant
} else {
    $requested = & python -m tools.build_variants select
}
if ($LASTEXITCODE -ne 0 -or -not $requested) {
    Write-Host "  ERROR: no build variant to build" -ForegroundColor Red
    exit 1
}
$requested = @($requested | ForEach-Object { $_.Trim() } | Where-Object { $_ })

# The version is derived, never written down, so there is no literal to parse.
# src/_version.py resolves it from the git tag and answers through the package.
$versionStr = "unknown"
try {
    $resolved = & python -c "import src; print(src.__version__)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) {
        $versionStr = ([string]($resolved | Select-Object -First 1)).Trim()
    }
} catch {
    # python absent or unimportable; the placeholder stands and the build runs
}
if (-not $versionStr) {
    $versionStr = "unknown"
}

Write-Host ""
Write-Host "  Acervator v$versionStr" -ForegroundColor Cyan
Write-Host "  Variants: $($requested -join ', ')" -ForegroundColor Cyan
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

# --- Step 4: Build each variant ---
#
# The spec reads $variantEnvVar, names the output after the version and the
# variant, and bakes the variant into the bundle.
$distRoot = Join-Path $PSScriptRoot "dist"
$before = @()
if (Test-Path $distRoot) {
    $before = Get-ChildItem -Path $distRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
}

$failed = @()
foreach ($v in $requested) {
    Write-Host ""
    Write-Host "  Building the $v variant..." -ForegroundColor Cyan
    Set-Item -Path "Env:\$variantEnvVar" -Value $v
    pyinstaller Acervator_win.spec --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: the $v build failed" -ForegroundColor Red
        $failed += $v
    }
}
Remove-Item -Path "Env:\$variantEnvVar" -ErrorAction SilentlyContinue

# --- Step 5: Strip MOTW from built exe and all dist files ---
if (Test-Path $distRoot) {
    Get-ChildItem -Path $distRoot -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
}

# --- Step 6: Add Defender exclusion for the output root ---
# The whole dist root, once, because each build adds another folder under it.
try {
    Add-MpPreference -ExclusionPath $distRoot -ErrorAction Stop
    Write-Host "  Defender exclusion added: $distRoot" -ForegroundColor Green
} catch {
    Write-Host "  Note: Run as Administrator to add Defender exclusion" -ForegroundColor Yellow
    Write-Host "  Or manually add this folder to Defender exclusions:" -ForegroundColor Yellow
    Write-Host "    $distRoot" -ForegroundColor White
}

# --- Step 7: Report what this run produced ---
Write-Host ""
$after = @()
if (Test-Path $distRoot) {
    $after = Get-ChildItem -Path $distRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }
}
$fresh = $after | Where-Object { $before -notcontains $_ }
if ($fresh) {
    Write-Host "  DONE. This run produced:" -ForegroundColor Green
    foreach ($name in $fresh) {
        Write-Host "    $distRoot\$name\$name.exe" -ForegroundColor Green
    }
} else {
    Write-Host "  No new build folder appeared under $distRoot" -ForegroundColor Yellow
}
if ($after) {
    Write-Host ""
    Write-Host "  All builds kept in dist:" -ForegroundColor Gray
    foreach ($name in $after) {
        Write-Host "    $name" -ForegroundColor Gray
    }
}
if ($failed) {
    Write-Host ""
    Write-Host "  Failed variants: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host ""
