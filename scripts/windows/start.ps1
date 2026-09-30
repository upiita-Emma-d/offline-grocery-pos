# Starts the POS with waitress (production WSGI server). Settings come from .env; the log goes to data\logs.
# Output is redirected by cmd.exe: PowerShell 5 turns stderr lines (waitress logs there) into errors.
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root
$port = 8008
if (Test-Path '.env') {
    $line = Select-String -Path '.env' -Pattern '^\s*POS_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($line) { $port = $line.Matches[0].Groups[1].Value }
}
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data\logs') | Out-Null
$py = '.venv\Scripts\python.exe'
cmd.exe /c "$py manage.py migrate --noinput >> data\logs\server.log 2>&1"
cmd.exe /c "$py -m waitress --listen=0.0.0.0:$port --threads=6 config.wsgi:application >> data\logs\server.log 2>&1"
