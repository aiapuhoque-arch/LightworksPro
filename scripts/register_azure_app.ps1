#Requires -Version 7.0
<#
.SYNOPSIS
    Creates and configures the Lightworks Pro Azure App Registration automatically.
    Uses the Graph REST API directly — no PowerShell module required.
    Run this once. You will be asked to sign in to Microsoft 365 via browser.
    Re-running is safe: if an app named "Lightworks Pro" already exists it is
    reused rather than duplicated.
#>
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host "  Lightworks Pro — Microsoft 365 App Registration"
Write-Host "============================================================"
Write-Host ""

# ── 1. Device-code flow via REST (no module dependency) ──────────────────────
# We use the well-known "Azure CLI" public client (04b07795-...) to request
# Application.ReadWrite.All on behalf of the signed-in user.
# This client is pre-consented in every tenant for delegated Graph scopes.
# /organizations/ is intentional — app creation requires a work/school account.
# End users will later sign in via the Python app using the /common/ endpoint,
# which also accepts personal Microsoft accounts.
$azureCliClientId = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
$scope            = "https://graph.microsoft.com/Application.ReadWrite.All offline_access"

Write-Host "You will now be asked to sign in to Microsoft."
Write-Host "Your screen reader will read the URL and code."
Write-Host "Open that URL in your browser, enter the code, and sign in."
Write-Host ""

# Request device code
$dcResponse = Invoke-RestMethod -Method POST `
    -Uri "https://login.microsoftonline.com/organizations/oauth2/v2.0/devicecode" `
    -ContentType "application/x-www-form-urlencoded" `
    -Body "client_id=$azureCliClientId&scope=$([Uri]::EscapeDataString($scope))"

Write-Host $dcResponse.message
Write-Host ""

# Poll for token (interval given by server, default 5 s)
$pollInterval = [int]($dcResponse.interval ?? 5)
$expiresIn    = [int]($dcResponse.expires_in ?? 900)
$deadline     = (Get-Date).AddSeconds($expiresIn)
$deviceCode   = $dcResponse.device_code
$accessToken  = $null

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $pollInterval
    try {
        $tokenResponse = Invoke-RestMethod -Method POST `
            -Uri "https://login.microsoftonline.com/organizations/oauth2/v2.0/token" `
            -ContentType "application/x-www-form-urlencoded" `
            -Body ("client_id=$azureCliClientId" +
                   "&grant_type=urn:ietf:params:oauth:grant-type:device_code" +
                   "&device_code=$([Uri]::EscapeDataString($deviceCode))") `
            -ErrorAction Stop
        $accessToken = $tokenResponse.access_token
        break
    } catch {
        $body    = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        $errCode = $body.error
        if ($errCode -eq "authorization_pending") { continue }
        if ($errCode -eq "slow_down")             { $pollInterval += 5; continue }
        if ($errCode -eq "expired_token") {
            Write-Host "The sign-in code has expired. Please run this script again."
            exit 1
        }
        if ($errCode -eq "authorization_declined") {
            Write-Host "Sign-in was declined. Please run this script again and complete the sign-in."
            exit 1
        }
        Write-Host "Sign-in failed: $($body.error_description)"
        exit 1
    }
}

if (-not $accessToken) {
    Write-Host "Sign-in timed out. Please run this script again."
    exit 1
}

Write-Host "Signed in successfully."
$headers = @{ Authorization = "Bearer $accessToken"; "Content-Type" = "application/json" }

# ── 2. Resolve required Graph permission IDs at runtime ───────────────────────
# Querying the Graph service principal avoids hardcoding GUIDs that can change.
Write-Host "Resolving Microsoft Graph permission IDs..."

$graphSpResp = Invoke-RestMethod -Method GET `
    -Uri ("https://graph.microsoft.com/v1.0/servicePrincipals" +
          "?`$filter=appId eq '00000003-0000-0000-c000-000000000000'" +
          "&`$select=id,oauth2PermissionScopes") `
    -Headers $headers `
    -ErrorAction Stop

$allScopes = $graphSpResp.value[0].oauth2PermissionScopes

# Scopes that mirror auth.py SCOPES + User.Read (needed for basic sign-in)
$neededScopes = @(
    "User.Read",
    "User.ReadBasic.All",
    "Calendars.Read",
    "Mail.Read",
    "Mail.Send",
    "MailboxSettings.Read",
    "Presence.ReadWrite",
    "Chat.Read",
    "Notes.ReadWrite",
    "People.Read",
    "Contacts.Read",
    "Tasks.ReadWrite",
    "Sites.Read.All",
    "offline_access"
)

$scopeObjects = $neededScopes | ForEach-Object {
    $name = $_
    $match = $allScopes | Where-Object { $_.value -eq $name } | Select-Object -First 1
    if (-not $match) {
        Write-Host "[WARN] Graph permission '$name' not found — skipping."
    } else {
        [PSCustomObject]@{ id = $match.id; type = "Scope" }
    }
} | Where-Object { $_ -ne $null }

$requiredResourceAccess = @(
    @{
        resourceAppId  = "00000003-0000-0000-c000-000000000000"  # Microsoft Graph
        resourceAccess = @($scopeObjects)
    }
)

# ── 3. Check for existing app to avoid duplicates ─────────────────────────────
Write-Host "Checking for existing app registration..."

$existingResp = Invoke-RestMethod -Method GET `
    -Uri ("https://graph.microsoft.com/v1.0/applications" +
          "?`$filter=displayName eq 'Lightworks Pro'" +
          "&`$select=id,appId,displayName") `
    -Headers $headers `
    -ErrorAction Stop

$app = $existingResp.value | Select-Object -First 1

if ($app) {
    Write-Host "Existing 'Lightworks Pro' app found (Client ID: $($app.appId))."
    Write-Host "Attempting to update permissions (requires app ownership or admin role)..."
    $patchBody = @{
        requiredResourceAccess = $requiredResourceAccess
        isFallbackPublicClient = $true
        publicClient           = @{
            redirectUris = @("https://login.microsoftonline.com/common/oauth2/nativeclient")
        }
    } | ConvertTo-Json -Depth 10
    try {
        Invoke-RestMethod -Method PATCH `
            -Uri "https://graph.microsoft.com/v1.0/applications/$($app.id)" `
            -Headers $headers `
            -Body $patchBody `
            -ErrorAction Stop | Out-Null
        Write-Host "Permissions and redirect URI updated."
    } catch {
        $errBody = $_.ErrorDetails.Message | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($errBody.error.code -eq "Authorization_RequestDenied") {
            Write-Host ""
            Write-Host "Note: You do not have permission to modify this app registration."
            Write-Host "That is OK — the app is already configured by your IT administrator."
            Write-Host "Continuing with the existing Client ID..."
            Write-Host ""
        } else {
            Write-Host "Warning: Could not update app registration: $($errBody.error.message)"
            Write-Host "Continuing with the existing Client ID..."
        }
    }
} else {
    # ── 4. Create the app ─────────────────────────────────────────────────────
    Write-Host "Creating app registration..."
    $appBody = @{
        displayName            = "Lightworks Pro"
        signInAudience         = "AzureADandPersonalMicrosoftAccount"
        isFallbackPublicClient = $true
        publicClient           = @{
            redirectUris = @("https://login.microsoftonline.com/common/oauth2/nativeclient")
        }
        requiredResourceAccess = $requiredResourceAccess
    } | ConvertTo-Json -Depth 10

    try {
        $app = Invoke-RestMethod -Method POST `
            -Uri "https://graph.microsoft.com/v1.0/applications" `
            -Headers $headers `
            -Body $appBody `
            -ErrorAction Stop
    } catch {
        Write-Host "Failed to create app registration:"
        Write-Host $_.ErrorDetails.Message
        exit 1
    }
    Write-Host "App created successfully."
}

$clientId = $app.appId
Write-Host "Client ID: $clientId"

# ── 5. Save client ID to Lightworks Pro config ────────────────────────────────
$configDir  = "$env:APPDATA\LightworksPro"
$configPath = "$configDir\config.json"

# Ensure the directory exists (Lightworks Pro creates it on first launch, but
# the user may be setting up before the first launch).
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json

    if ($config.PSObject.Properties["microsoft_client_id"]) {
        $config.microsoft_client_id = $clientId
    } else {
        $config | Add-Member -NotePropertyName "microsoft_client_id" -NotePropertyValue $clientId
    }

    if ($config.PSObject.Properties["microsoft_tenant_id"]) {
        $config.microsoft_tenant_id = "common"
    } else {
        $config | Add-Member -NotePropertyName "microsoft_tenant_id" -NotePropertyValue "common"
    }

    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8
    Write-Host "Saved to $configPath"
} else {
    Write-Host ""
    Write-Host "[WARN] Config file not found at $configPath"
    Write-Host "       Launch Lightworks Pro once to create it, then re-run this script."
    Write-Host "       Or add this manually to config.json:"
    Write-Host "       `"microsoft_client_id`": `"$clientId`""
}

# ── 6. Done ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================"
Write-Host "  DONE"
Write-Host "  Restart Lightworks Pro to connect Microsoft 365."
Write-Host "  On first use (calendar or inbox), it will ask you to"
Write-Host "  sign in one more time. After that it stays connected."
Write-Host "============================================================"
Write-Host ""
