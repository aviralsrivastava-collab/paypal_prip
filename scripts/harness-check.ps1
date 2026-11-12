$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$required = @(
  'AGENTS.md',
  '.agents/rules/01-project-scope.md',
  '.agents/rules/02-architecture.md',
  '.agents/rules/03-security-and-trust.md',
  '.agents/rules/06-testing-and-quality.md',
  '.agents/skills/feature-implementation/SKILL.md',
  'docs/PRODUCT_SPEC.md',
  'docs/ARCHITECTURE.md',
  'docs/SECURITY.md',
  'docs/TESTING_STRATEGY.md',
  'docs/ACCEPTANCE_CRITERIA.md'
)

$missing = @()
foreach ($item in $required) {
  if (-not (Test-Path (Join-Path $root $item))) { $missing += $item }
}
if ($missing.Count -gt 0) {
  Write-Host 'Harness structure check FAILED. Missing:' -ForegroundColor Red
  $missing | ForEach-Object { Write-Host " - $_" }
  exit 1
}

$forbidden = @('.env', '.env.local', '.env.production', 'id_rsa', 'id_ed25519')
$found = @()
foreach ($item in $forbidden) {
  if (Test-Path (Join-Path $root $item)) { $found += $item }
}
if ($found.Count -gt 0) {
  Write-Host 'Potentially sensitive files exist. Confirm they are ignored and never committed:' -ForegroundColor Yellow
  $found | ForEach-Object { Write-Host " - $_" }
}

$trackedEnv = @()
if (Get-Command git -ErrorAction SilentlyContinue) {
  $isGitRepo = $false
  try {
    if (Test-Path (Join-Path $root '.git')) {
      $isGitRepo = $true
    } else {
      $null = cmd /c "git rev-parse --is-inside-work-tree 2>nul"
      if ($LASTEXITCODE -eq 0) {
        $isGitRepo = $true
      }
    }
  } catch {
    $isGitRepo = $false
  }

  if ($isGitRepo) {
    # Narrow exceptions for verified non-secret template and scanning tooling:
    # - .env.example: Authorized environment template containing only non-secret placeholders
    # - frontend/.env.example: Authorized frontend environment template
    # - scripts/secrets_scan.py: Dedicated multi-pattern secret scanner utility
    $exemptTrackedFiles = @('.env.example', 'frontend/.env.example', 'scripts/secrets_scan.py')
    $tracked = git ls-files 2>$null
    foreach ($path in $tracked) {
      $normalized = $path.Replace('\', '/')
      if ($exemptTrackedFiles -contains $normalized) { continue }
      if ($normalized -match '(^|/)(\.env($|\.)|.*(secret|credential|private.?key).*)') { $trackedEnv += $normalized }
    }
  } else {
    Write-Host 'Git repository not detected; skipping tracked-files secret scan.' -ForegroundColor Yellow
  }
}
if ($trackedEnv.Count -gt 0) {
  Write-Host 'Review tracked paths that may contain secrets:' -ForegroundColor Red
  $trackedEnv | ForEach-Object { Write-Host " - $_" }
  exit 2
}

if (Test-Path (Join-Path $root 'scripts/secrets_scan.py')) {
  Write-Host 'Running automated secrets scan...' -ForegroundColor Cyan
  $pyCmd = 'python'
  if (Test-Path (Join-Path $root '.venv/Scripts/python.exe')) {
    $pyCmd = (Join-Path $root '.venv/Scripts/python.exe')
  }
  & $pyCmd (Join-Path $root 'scripts/secrets_scan.py')
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'Automated secrets scan FAILED.' -ForegroundColor Red
    exit 1
  }
}

Write-Host 'Harness structure check passed. This does NOT run application tests or prove security.' -ForegroundColor Green
