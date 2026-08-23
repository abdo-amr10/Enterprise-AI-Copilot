<#!
.SYNOPSIS
Starts the AI Runtime after loading optional local configuration from ai/.env.

.DESCRIPTION
The .env file is intentionally local and is not committed. This script only
loads simple KEY=VALUE lines; operating-system environment variables take
precedence so deployed environments can configure the service normally.
#>

[CmdletBinding()]
param(
    [int]$Port = 8000
)

$aiRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $aiRoot '.env'

if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line -split '=', 2
        if ($parts.Count -ne 2) { throw "Invalid .env line: $line" }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Push-Location $aiRoot
try {
    python -m uvicorn main:app --host 0.0.0.0 --port $Port
}
finally {
    Pop-Location
}
