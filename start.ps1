# Activate venv
$venvPath = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
& $venvPath

function Load-DotEnv {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return
  }

  $dotenvCode = @'
import json, sys
from dotenv import dotenv_values
print(json.dumps({k: v for k, v in dotenv_values(sys.argv[1]).items() if v is not None}))
'@
  $dotenvJson = & (Join-Path $PSScriptRoot "venv\Scripts\python.exe") -c $dotenvCode $Path
  if ($LASTEXITCODE -ne 0) {
    throw "Could not load .env."
  }

  $dotenvValues = $dotenvJson | ConvertFrom-Json
  foreach ($entry in $dotenvValues.PSObject.Properties) {
    [System.Environment]::SetEnvironmentVariable($entry.Name, [string]$entry.Value, "Process")
  }
}

function Get-BooleanEnv {
  param(
    [string]$Name,
    [bool]$DefaultValue
  )

  $rawValue = [System.Environment]::GetEnvironmentVariable($Name, "Process")
  if ([string]::IsNullOrWhiteSpace($rawValue)) {
    return $DefaultValue
  }

  return @("1", "true", "yes", "on") -contains $rawValue.Trim().ToLowerInvariant()
}

Load-DotEnv -Path (Join-Path $PSScriptRoot ".env")

$backendHost = [System.Environment]::GetEnvironmentVariable("BACKEND_DEV_HOST", "Process")
if ([string]::IsNullOrWhiteSpace($backendHost)) {
  $backendHost = "localhost"
}

$backendPort = [System.Environment]::GetEnvironmentVariable("BACKEND_DEV_PORT", "Process")
if ([string]::IsNullOrWhiteSpace($backendPort)) {
  $backendPort = "8000"
}

$useHttps = Get-BooleanEnv -Name "BACKEND_DEV_USE_HTTPS" -DefaultValue $true
$uvicornArgs = @(
  "config.asgi:application",
  "--host", $backendHost,
  "--port", $backendPort
)

if ($useHttps) {
  $uvicornArgs += @(
    "--ssl-keyfile", (Join-Path $PSScriptRoot "certs\localhost-key.pem"),
    "--ssl-certfile", (Join-Path $PSScriptRoot "certs\localhost.pem")
  )
}

& uvicorn @uvicornArgs
