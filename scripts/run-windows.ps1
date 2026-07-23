$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
if (-not (Test-Path ".venv")) { py -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
$env:CRYPTOGOTCHI_CONFIG = "$Root\.dev\config.toml"
$env:CRYPTOGOTCHI_DATA_DIR = "$Root\.dev\data"
New-Item -ItemType Directory -Force -Path "$Root\.dev\data" | Out-Null
& ".\.venv\Scripts\python.exe" -m cryptogotchi
