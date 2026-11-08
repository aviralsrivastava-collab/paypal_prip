$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host 'PRIP verification launcher'
Write-Host 'This script only runs test commands that are discoverable from repository manifests.'
Write-Host 'Review commands before running if this repository has custom scripts.'

$ran = 0
if ((Test-Path 'backend/pyproject.toml') -or (Test-Path 'pyproject.toml')) {
  $pytestCmd = $null
  if (Test-Path '.venv/Scripts/pytest.exe') {
    $pytestCmd = '.venv/Scripts/pytest.exe'
  } elseif (Get-Command pytest -ErrorAction SilentlyContinue) {
    $pytestCmd = 'pytest'
  }

  if ($pytestCmd) {
    Write-Host "Running pytest via $pytestCmd..."
    & $pytestCmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $ran++
  } else {
    Write-Warning 'Python project detected but pytest is not on PATH or .venv; Python tests not run.'
  }
}

if (Test-Path 'frontend/package.json') {
  $npmCmd = $null
  if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    $npmCmd = 'npm.cmd'
  } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $npmCmd = 'npm'
  }

  if (-not $npmCmd) {
    Write-Warning 'Frontend package.json found but npm is unavailable; frontend tests not run.'
  } else {
    $pkg = Get-Content 'frontend/package.json' -Raw | ConvertFrom-Json
    if ($pkg.scripts -and $pkg.scripts.test) {
      Push-Location 'frontend'
      try {
        & $npmCmd test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $ran++
      } finally { Pop-Location }
    } else {
      Write-Warning 'No frontend test script found; frontend tests not run.'
    }
  }
}

if ($ran -eq 0) {
  Write-Warning 'No configured test command was executed. Discover the actual project commands and run them manually.'
  exit 3
}
Write-Host "Verification commands completed: $ran. Add lint/type/build/integration checks from the actual repository configuration." -ForegroundColor Green
