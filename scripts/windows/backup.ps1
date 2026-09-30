# Daily verified backup (scheduled by install.ps1). Keeps the newest 30 copies in data\backups and,
# if POS_BACKUP_DIR is set in .env (for example a USB drive), 30 more there.
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $Root
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data\logs') | Out-Null
$py = '.venv\Scripts\python.exe'
cmd.exe /c "$py manage.py backup --dest data\backups --keep 30 >> data\logs\backup.log 2>&1"
$extra = Select-String -Path '.env' -Pattern '^\s*POS_BACKUP_DIR\s*=\s*(.+)$' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($extra) {
    $dest = $extra.Matches[0].Groups[1].Value.Trim()
    if (Test-Path (Split-Path $dest -Qualifier)) {
        cmd.exe /c "$py manage.py backup --dest `"$dest`" --keep 30 >> data\logs\backup.log 2>&1"
    } else {
        Add-Content -Encoding UTF8 'data\logs\backup.log' "$(Get-Date -Format s) Backup drive $dest not connected; only the local copy was made."
    }
}
