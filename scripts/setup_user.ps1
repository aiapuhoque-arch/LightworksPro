#Requires -Version 5.1
<#
.SYNOPSIS
    Configures Lightworks Pro on a new user's machine.
    No admin rights, no Azure permissions, no browser sign-in required.
    Run this ONCE per machine. The IT administrator runs register_azure_app.ps1
    only once to create the Azure App Registration — all other users run this script.

.PARAMETER ClientId
    The Azure App Client ID for your organisation's Lightworks Pro registration.
    Your IT administrator provides this value after running register_azure_app.ps1.

.EXAMPLE
    .\setup_user.ps1 -ClientId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
#>
param(
    [string]$ClientId = ""
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================"
Write-Host "  Lightworks Pro — User Setup"
Write-Host "============================================================"
Write-Host ""

if (-not $ClientId) {
    Write-Host "ERROR: No Client ID provided."
    Write-Host "Ask your IT administrator for the Lightworks Pro Client ID"
    Write-Host "and run:  .\setup_user.ps1 -ClientId YOUR-CLIENT-ID"
    exit 1
}

$configDir  = "$env:APPDATA\LightworksPro"
$configPath = "$configDir\config.json"

# Create config directory if it does not exist yet
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

# Update existing config or create a fresh one
if (Test-Path $configPath) {
    Write-Host "Existing config found — updating Microsoft 365 credentials..."
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
    } catch {
        Write-Host "Warning: existing config.json could not be parsed — creating a new one."
        $config = [PSCustomObject]@{}
    }

    if ($config.PSObject.Properties["microsoft_client_id"]) {
        $config.microsoft_client_id = $ClientId
    } else {
        $config | Add-Member -NotePropertyName "microsoft_client_id" -NotePropertyValue $ClientId
    }

    if ($config.PSObject.Properties["microsoft_tenant_id"]) {
        $config.microsoft_tenant_id = "common"
    } else {
        $config | Add-Member -NotePropertyName "microsoft_tenant_id" -NotePropertyValue "common"
    }

    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8

} else {
    Write-Host "Creating new config..."
    @{
        microsoft_client_id = $ClientId
        microsoft_tenant_id = "common"
        tts                 = @{ rate = 200; volume = 1.0 }
        audio_duck_volume   = 0.2
        log_level           = "INFO"
    } | ConvertTo-Json -Depth 5 | Set-Content $configPath -Encoding UTF8
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  DONE — Lightworks Pro is configured."
Write-Host ""
Write-Host "  Next step:"
Write-Host "  Launch Lightworks Pro. On first use it will ask you to"
Write-Host "  sign in to Microsoft 365 in your browser — this takes"
Write-Host "  about 30 seconds and only happens once."
Write-Host "============================================================"
Write-Host ""
