# Activate venv
$venvPath = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
& $venvPath

function Load-DotEnv {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    return
  }

  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()

    if (-not $line -or $line.StartsWith("#")) {
      return
    }

    $parts = $line -split "=", 2
    if ($parts.Length -ne 2) {
      return
    }

    [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
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
