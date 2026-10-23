param([string]$AppName = "instant-refund-api")

Write-Host "`nGenerating secure secrets..." -ForegroundColor Cyan

# Generate secrets using Windows crypto
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$buf48 = New-Object byte[] 48
$buf32a = New-Object byte[] 32
$buf32b = New-Object byte[] 32
$rng.GetBytes($buf48)
$rng.GetBytes($buf32a)
$rng.GetBytes($buf32b)

$SECRET_KEY           = [Convert]::ToBase64String($buf48)
$SIGNER_SHARED_SECRET = [Convert]::ToBase64String($buf48)
$API_KEY_1            = [BitConverter]::ToString($buf32a).Replace("-","").ToLower()
$API_KEY_2            = [BitConverter]::ToString($buf32b).Replace("-","").ToLower()
$API_KEYS             = "$API_KEY_1,$API_KEY_2"

Write-Host "[OK] Secrets generated" -ForegroundColor Green

# Prompt for infrastructure values
Write-Host "`nEnter infrastructure values (press Enter to skip optional ones):" -ForegroundColor Yellow
$DATABASE_URL              = Read-Host "  DATABASE_URL (postgres://...)"
$SIGNER_URL                = Read-Host "  SIGNER_URL (http://localhost:8001 or signer endpoint)"
$KASPA_RPC_HOST            = Read-Host "  KASPA_RPC_HOST [your-kaspad-host]"
if (-not $KASPA_RPC_HOST) { $KASPA_RPC_HOST = "your-kaspad-host" }
$KASPA_RPC_PORT            = Read-Host "  KASPA_RPC_PORT [16110]"
if (-not $KASPA_RPC_PORT) { $KASPA_RPC_PORT = "16110" }
$KASPA_NETWORK             = Read-Host "  KASPA_NETWORK [mainnet]"
if (-not $KASPA_NETWORK) { $KASPA_NETWORK = "mainnet" }
$KASPA_REFUND_FROM_ADDRESS = Read-Host "  KASPA_REFUND_FROM_ADDRESS"
$KASPAD_ADDRESS            = Read-Host "  KASPAD_ADDRESS [your-kaspad-host]"
if (-not $KASPAD_ADDRESS) { $KASPAD_ADDRESS = "your-kaspad-host" }
$CORS_ORIGINS              = Read-Host "  CORS_ORIGINS (e.g. https://yourdomain.com)"
if (-not $CORS_ORIGINS) { $CORS_ORIGINS = "*" }
$RATE_LIMIT                = Read-Host "  RATE_LIMIT [60/minute]"
if (-not $RATE_LIMIT) { $RATE_LIMIT = "60/minute" }

# Get app ID
Write-Host "`nLooking up app ID for '$AppName'..." -ForegroundColor Cyan
$appId = doctl apps list --format ID,Spec.Name --no-header 2>$null |
    Where-Object { $_ -match $AppName } |
    ForEach-Object { ($_ -split '\s+')[0] } |
    Select-Object -First 1

if (-not $appId) {
    Write-Error "Could not find app '$AppName'. Run: doctl apps list"
    exit 1
}
Write-Host "[OK] App ID: $appId" -ForegroundColor Green

# Build env vars array
$envVars = @(
    @{key="SECRET_KEY";                value=$SECRET_KEY;                type="SECRET"},
    @{key="SIGNER_SHARED_SECRET";      value=$SIGNER_SHARED_SECRET;      type="SECRET"},
    @{key="API_KEYS";                  value=$API_KEYS;                  type="SECRET"},
    @{key="DATABASE_URL";              value=$DATABASE_URL;              type="SECRET"},
    @{key="SIGNER_URL";                value=$SIGNER_URL;                type="GENERAL"},
    @{key="KASPA_RPC_HOST";            value=$KASPA_RPC_HOST;            type="GENERAL"},
    @{key="KASPA_RPC_PORT";            value=$KASPA_RPC_PORT;            type="GENERAL"},
    @{key="KASPA_NETWORK";             value=$KASPA_NETWORK;             type="GENERAL"},
    @{key="KASPA_REFUND_FROM_ADDRESS"; value=$KASPA_REFUND_FROM_ADDRESS; type="GENERAL"},
    @{key="KASPAD_ADDRESS";            value=$KASPAD_ADDRESS;            type="GENERAL"},
    @{key="CORS_ORIGINS";              value=$CORS_ORIGINS;              type="GENERAL"},
    @{key="RATE_LIMIT";                value=$RATE_LIMIT;                type="GENERAL"},
    @{key="ENABLE_DOCS";               value="false";                    type="GENERAL"},
    @{key="WORKER_POLL_SECONDS";       value="2";                        type="GENERAL"}
)

# Apply each env var via doctl
Write-Host "`nSetting environment variables..." -ForegroundColor Cyan
foreach ($ev in $envVars) {
    if (-not $ev.value) { Write-Warning "  SKIP $($ev.key) (empty)"; continue }
    $result = doctl apps update $appId --spec - 2>&1
    doctl apps create-deployment $appId 2>$null | Out-Null
    Write-Host "  [OK] $($ev.key)" -ForegroundColor Green
}

# Use doctl to set env vars properly via spec update
$specFile = "$env:TEMP\do-app-spec.json"
doctl apps spec get $appId --format json 2>$null | Out-File $specFile -Encoding UTF8

$spec = Get-Content $specFile -Raw | ConvertFrom-Json
$envArray = $envVars | Where-Object { $_.value } | ForEach-Object {
    [PSCustomObject]@{ key = $_.key; value = $_.value; type = $_.type; scope = "RUN_AND_BUILD_TIME" }
}

# Apply to all services in the spec
foreach ($svc in $spec.services) {
    $svc.envs = $envArray
}

$spec | ConvertTo-Json -Depth 20 | Out-File $specFile -Encoding UTF8
doctl apps update $appId --spec $specFile
Write-Host "`n[OK] Env vars applied to app spec" -ForegroundColor Green

# Trigger redeploy
Write-Host "Triggering redeploy..." -ForegroundColor Cyan
doctl apps create-deployment $appId
Write-Host "[OK] Deployment triggered" -ForegroundColor Green

# Save API keys locally
$keyFile = "C:\Users\brian\instant-refund\instant-refund\instant-refund-api-keys.txt"
@"
INSTANT REFUND API KEYS - DO NOT COMMIT
Generated: $(Get-Date)

API_KEY_1: $API_KEY_1
API_KEY_2: $API_KEY_2

Use X-API-Key header with either key to authenticate requests.
"@ | Set-Content $keyFile
Write-Host "`nAPI keys saved to: $keyFile" -ForegroundColor Yellow
Write-Host "WARNING: Do not commit this file to git!" -ForegroundColor Red
