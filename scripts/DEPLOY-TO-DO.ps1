# =============================================================================
# DEPLOY-TO-DO.ps1
# Full deployment pipeline for Instant Refund API security remediation.
#
# WHAT IT DOES (in order):
#   1. Validates your local git repo and DO CLI are ready
#   2. Runs all 9 security fix scripts against your local project files
#   3. Git commits the changes with a clear audit message
#   4. Git pushes to GitHub (DO App Platform auto-deploys on push)
#   5. Optionally force-triggers DO App Platform deploy via doctl
#   6. Prints live deploy status
#
# USAGE (run from your LOCAL Windows PowerShell):
#   .\scripts\DEPLOY-TO-DO.ps1 -ProjectRoot "C:\path\to\instant-refund" -AppName "instant-refund"
#
# REQUIREMENTS:
#   - doctl installed and authenticated (https://docs.digitalocean.com/reference/doctl/how-to/install/)
#   - git installed and repo already cloned locally
#   - SSH access to droplet (for env var validation)
#
# DROPLET IPs (from your project):
#   - API / demo server: your-droplet-ip
#   - Kaspad node / sidecar: your-kaspad-host
# =============================================================================

#Requires -Version 5.1

param(
    # REQUIRED: Path to your local instant-refund repo root
    [Parameter(Mandatory=$true)]
    [string]$ProjectRoot,

    # REQUIRED: Your DO App Platform app name (from `doctl apps list`)
    [Parameter(Mandatory=$true)]
    [string]$AppName,

    # OPTIONAL: Your DO droplet IP (demo/API server) — for env var check
    [string]$DropletHost = "your-droplet-ip",

    [string]$DropletUser = "root",

    # OPTIONAL: Skip running fix scripts (if already applied)
    [switch]$SkipFixes,

    # OPTIONAL: Skip git push (dry run the fixes only)
    [switch]$SkipPush,

    # OPTIONAL: Force DO redeploy even if push already triggered it
    [switch]$ForceRedeploy
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot  # Same folder as this script

Write-Host @"

  ╔══════════════════════════════════════════════════════════════╗
  ║  Instant Refund — Security Remediation Deployment Pipeline   ║
  ║  Target: DigitalOcean App Platform + Droplet                 ║
  ╚══════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# STEP 1 — Validate prerequisites
# ---------------------------------------------------------------------------
Write-Host "[STEP 1] Validating prerequisites..." -ForegroundColor White

# Check git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git not found. Install from https://git-scm.com/"
    exit 1
}
Write-Host "  [OK] git found: $(git --version)"

# Check doctl (optional but highly recommended)
$doctlAvailable = $null -ne (Get-Command doctl -ErrorAction SilentlyContinue)
if ($doctlAvailable) {
    Write-Host "  [OK] doctl found: $(doctl version 2>&1 | Select-Object -First 1)"
} else {
    Write-Warning "  [WARN] doctl not found — will rely on git push to trigger deploy."
    Write-Warning "  Install from: https://docs.digitalocean.com/reference/doctl/how-to/install/"
}

# Check project root
if (-not (Test-Path $ProjectRoot)) {
    Write-Error "ProjectRoot not found: $ProjectRoot"
    exit 1
}

$gitDir = Join-Path $ProjectRoot ".git"
if (-not (Test-Path $gitDir)) {
    Write-Error "$ProjectRoot is not a git repository (no .git folder)"
    exit 1
}
Write-Host "  [OK] Git repo found at: $ProjectRoot"

# Confirm clean-ish working tree (warn if uncommitted changes already exist)
Push-Location $ProjectRoot
$status = git status --porcelain
if ($status) {
    Write-Warning "  [WARN] Uncommitted changes already exist in repo:"
    $status | Select-Object -First 10 | ForEach-Object { Write-Warning "    $_" }
    $confirm = Read-Host "  Continue anyway? The fix scripts will add more changes. (y/N)"
    if ($confirm -ne 'y') { Pop-Location; exit 0 }
}
Pop-Location

# ---------------------------------------------------------------------------
# STEP 2 — Run security fix scripts
# ---------------------------------------------------------------------------
if ($SkipFixes) {
    Write-Host "`n[STEP 2] Skipping fix scripts (-SkipFixes set)" -ForegroundColor Yellow
} else {
    Write-Host "`n[STEP 2] Running security fix scripts..." -ForegroundColor White
    $masterScript = Join-Path $ScriptsDir "RUN-ALL-FIXES.ps1"
    if (-not (Test-Path $masterScript)) {
        Write-Error "RUN-ALL-FIXES.ps1 not found at: $masterScript"
        exit 1
    }
    & $masterScript -ProjectRoot $ProjectRoot
    Write-Host "`n  [OK] Fix scripts completed." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# STEP 3 — Git commit
# ---------------------------------------------------------------------------
if ($SkipPush) {
    Write-Host "`n[STEP 3/4] Skipping git commit and push (-SkipPush set)" -ForegroundColor Yellow
} else {
    Write-Host "`n[STEP 3] Committing security fixes to git..." -ForegroundColor White
    Push-Location $ProjectRoot

    git add -A
    $changed = git status --porcelain
    if (-not $changed) {
        Write-Host "  [SKIP] No changes to commit — fixes may already be applied." -ForegroundColor Yellow
    } else {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        $commitMsg = "security: apply audit remediation fixes ($timestamp)

Changes:
- Critical: remove hardcoded secrets and Kaspa node IP
- Critical: validate required env vars on startup
- High: add X-API-Key authentication to all refund endpoints
- High: add slowapi rate limiting (60/min per IP)
- High: amount validation with Decimal type
- High: remove /debug and /__debug endpoints
- High: sanitize exception responses (no str(e) leakage)
- High: remove empty HMAC fallback in worker
- Medium: CORS allowlist via CORS_ORIGINS env var
- Medium: thread-safe sanctions cache with TTL
- Medium: raise_for_status() on external API calls
- Low: structured logging (no print statements)
- Low: fix silent exception in BIN loader"

        git commit -m $commitMsg
        Write-Host "  [OK] Committed changes." -ForegroundColor Green
    }

    # ---------------------------------------------------------------------------
    # STEP 4 — Git push
    # ---------------------------------------------------------------------------
    Write-Host "`n[STEP 4] Pushing to GitHub (DO App Platform will auto-deploy)..." -ForegroundColor White
    git push
    Write-Host "  [OK] Pushed to GitHub." -ForegroundColor Green
    Pop-Location
}

# ---------------------------------------------------------------------------
# STEP 5 — Force DO App Platform deploy (optional, via doctl)
# ---------------------------------------------------------------------------
if ($doctlAvailable -and ($ForceRedeploy -or -not $SkipPush)) {
    Write-Host "`n[STEP 5] Triggering DO App Platform deploy via doctl..." -ForegroundColor White

    # Get app ID from app name
    try {
        $appsJson = doctl apps list --output json 2>&1
        $apps = $appsJson | ConvertFrom-Json
        $app = $apps | Where-Object { $_.spec.name -eq $AppName } | Select-Object -First 1

        if (-not $app) {
            Write-Warning "  App '$AppName' not found via doctl. Available apps:"
            $apps | ForEach-Object { Write-Warning "    - $($_.spec.name)" }
        } else {
            $appId = $app.id
            Write-Host "  App ID: $appId"
            doctl apps create-deployment $appId --force-rebuild
            Write-Host "  [OK] Deploy triggered." -ForegroundColor Green

            # Poll for deploy status (up to 5 mins)
            Write-Host "  Waiting for deploy to start..."
            Start-Sleep -Seconds 10
            $deploy = doctl apps list-deployments $appId --output json | ConvertFrom-Json | Select-Object -First 1
            Write-Host "  Deploy status: $($deploy.phase)"
        }
    } catch {
        Write-Warning "  doctl deploy trigger failed: $_"
        Write-Warning "  You can trigger manually in DO dashboard: Apps → $AppName → Deploy"
    }
} else {
    Write-Host "`n[STEP 5] DO App Platform will auto-deploy from your git push." -ForegroundColor Yellow
    Write-Host "  Monitor at: https://cloud.digitalocean.com/apps"
}

# ---------------------------------------------------------------------------
# Final checklist reminder
# ---------------------------------------------------------------------------
Write-Host @"

╔══════════════════════════════════════════════════════════════════════╗
║  DEPLOYMENT COMPLETE — FINAL CHECKLIST                               ║
╚══════════════════════════════════════════════════════════════════════╝

  1. Set environment variables in DO App Platform (CRITICAL — do this NOW):
     Run: .\scripts\SET-DO-ENV-VARS.ps1 -AppName "$AppName"

  2. Verify deploy succeeded:
     https://cloud.digitalocean.com/apps  (watch for green deploy)

  3. Test authentication:
     curl -H "X-API-Key: YOUR_KEY" https://your-app.ondigitalocean.app/v1/refunds/instant

  4. Remaining manual fixes (can't be scripted):
     - static/index.html lines 22,37: remove hardcoded wallet addresses
     - app/tools/wallet_validator.py: add per-chain checksum verification

  5. Droplet (your-droplet-ip) env vars are separate — run SET-DO-ENV-VARS.ps1
     with -AlsoConfigureDroplet to handle both.

"@ -ForegroundColor Yellow
