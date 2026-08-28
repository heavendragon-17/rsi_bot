$ErrorActionPreference = "Stop"

# ---- Find Python ----

if (Get-Command python -ErrorAction SilentlyContinue) {
    $PYTHON = "python"
}
elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PYTHON = "python3"
}
else {
    Write-Error "Python not found. Install Python 3.13+"
    exit 1
}

$PythonVersion = & $PYTHON -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ([version]$PythonVersion -lt [version]"3.13") {
    Write-Error "Python 3.13+ is required; found $PythonVersion"
    exit 1
}

Write-Host "Using Python executable: $PYTHON ($PythonVersion)"

# ---- Create venv ----
& $PYTHON -m venv venv

# ---- Activate venv ----
. .\venv\Scripts\Activate.ps1

# ---- Upgrade pip ----
python -m pip install --upgrade pip

# ---- Install dependencies ----
python -m pip install -r requirements.txt

Write-Host "Environment ready (PowerShell)"
