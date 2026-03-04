$ErrorActionPreference = "Stop"

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

echo "Using Python executable: $PYTHON"

# ---- Create venv ----
& $PYTHON -m venv venv

# ---- Activate venv ----
. .\venv\Scripts\Activate.ps1

# ---- Upgrade pip ----
python -m pip install --upgrade pip

# ---- Install dependencies ----
pip install -r requirements.txt

Write-Host "Environment ready (PowerShell)"