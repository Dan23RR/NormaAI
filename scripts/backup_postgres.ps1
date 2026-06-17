# NormaAI - daily Postgres backup (custom-format dump + 30-day retention).
# Schedule via Task Scheduler (see docs/BACKUP_STRATEGY.md). Safe to run manually.
#
# Exit codes: 0 ok · 1 dump failed · 2 verify failed

$ErrorActionPreference = 'Stop'

$repoRoot   = Split-Path -Parent $PSScriptRoot
$backupDir  = Join-Path $repoRoot 'backups'
$container  = 'normaai-postgres'
$dbUser     = 'normaai'
$dbName     = 'normaai'
$retention  = 30  # days

New-Item -ItemType Directory -Force $backupDir | Out-Null

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$file  = Join-Path $backupDir "normaai_$stamp.dump"

Write-Host "[backup] dumping $dbName from $container -> $file"
# Custom format (-Fc): compressed, supports selective/parallel restore.
docker exec $container pg_dump -U $dbUser -d $dbName -Fc --no-owner | Set-Content -Path $file -AsByteStream
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $file)) {
    Write-Error "[backup] pg_dump FAILED"
    exit 1
}

$sizeKb = [math]::Round((Get-Item $file).Length / 1KB)
if ($sizeKb -lt 5) {
    Write-Error "[backup] dump suspiciously small ($sizeKb KB) - treating as failure"
    exit 2
}

# Integrity check: pg_restore must be able to read the archive TOC.
Get-Content $file -AsByteStream -ReadCount 0 | docker exec -i $container pg_restore --list > $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "[backup] verify FAILED (pg_restore --list could not read archive)"
    exit 2
}
Write-Host "[backup] OK ($sizeKb KB, verified)"

# Retention: delete dumps older than $retention days.
Get-ChildItem $backupDir -Filter 'normaai_*.dump' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$retention) } |
    ForEach-Object {
        Write-Host "[backup] pruning $($_.Name)"
        Remove-Item $_.FullName -Force
    }

exit 0
