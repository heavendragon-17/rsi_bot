#!/usr/bin/env bash

ENV_FILE="env.txt"

# ---- Load env vars ----
while IFS='=' read -r key value; do
    # Skip empty lines and comments
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue

    export "$key=$value"
done < "$ENV_FILE"

# ---- Check Python ----
if command -v python >/dev/null 2>&1; then
    PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    echo "Python not found. Please install Python 3.9+"
    exit 1
fi

# ---- Create venv ----
$PYTHON -m venv .venv

# ---- Activate venv ----
source .venv/bin/activate

# ---- Upgrade pip ----
pip install --upgrade pip

# ---- Install dependencies ----
pip install -r requirements.txt

echo "Environment ready (Linux)"
