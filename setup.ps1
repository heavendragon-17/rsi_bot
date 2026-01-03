$ErrorActionPreference = "Stop"

$EnvFile = "env.txt"

# ---- Load env vars ----
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $_ = $_.Trim()

        if ($_ -and -not $_.StartsWith("#")) {
            $name, $value = $_ -split "=", 2
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Write-Host "Loaded environment variables from $EnvFile"
}
else {
    Write-Host "Env file not found: $EnvFile"
}

# ---- Find Python ----

if (Get-Command python -ErrorAction SilentlyContinue) {
    $PYTHON = "python"
}
elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PYTHON = "python3"
}
else {
    Write-Error "Python not found. Install Python 3.9+"
    exit 1
}

# ---- Create venv ----
& $PYTHON -m venv .venv

# ---- Activate venv ----
. .\.venv\Scripts\Activate.ps1

# ---- Upgrade pip ----
python -m pip install --upgrade pip

# ---- Install dependencies ----
pip install -r requirements.txt

Write-Host "Environment ready (PowerShell)"
