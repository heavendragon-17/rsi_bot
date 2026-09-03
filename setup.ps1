$ErrorActionPreference = "Stop"

# ---- Find Python (prefers newest >= 3.13, supports py launcher) ----

function Get-CandidateVersion($Exe, $ExtraArgs) {
    try {
        $out = & $Exe @ExtraArgs -c "import sys; print('.'.join(map(str, sys.version_info[:3]))); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out -or $out.Count -lt 2) { return $null }
        return @{ Version = [version]$out[0].Trim(); ExePath = $out[1].Trim() }
    } catch { return $null }
}

$candidates = @(
    @{ Exe = "py"; Args = @("-3.14") },
    @{ Exe = "py"; Args = @("-3.13") },
    @{ Exe = "py"; Args = @("-3") },
    @{ Exe = "python"; Args = @() },
    @{ Exe = "python3"; Args = @() }
)

$Best = $null
foreach ($c in $candidates) {
    if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
    $info = Get-CandidateVersion $c.Exe $c.Args
    if ($null -eq $info) { continue }
    if ($info.Version -lt [version]"3.13") {
        Write-Host "Skipping $($c.Exe) $($c.Args -join ' '): found $($info.Version) at $($info.ExePath) (< 3.13)"
        continue
    }
    if ($null -eq $Best -or $info.Version -gt $Best.Version) {
        $Best = $info
        $PYTHON = $info.ExePath
    }
}

if ($null -eq $Best) {
    $foundVer = try { & python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null } catch { "unknown" }
    Write-Host "Python 3.13+ is required; found $foundVer (`python --version`). But you may have 3.14 via the `py` launcher - this script now checks that." -ForegroundColor Red
    Write-Host "Diagnose with: python --version; py --version; py -0p; Get-Command python,py" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python executable: $PYTHON ($($Best.Version))"

# ---- Create venv ----
& $PYTHON -m venv venv

# ---- Activate venv ----
. .\venv\Scripts\Activate.ps1

# ---- Upgrade pip ----
python -m pip install --upgrade pip

# ---- Install dependencies ----
python -m pip install -r requirements.txt

Write-Host "Environment ready (PowerShell)"
