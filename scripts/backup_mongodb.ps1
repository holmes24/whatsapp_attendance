param(
  [string]$MongoUri = $env:MONGODB_BACKUP_URI,
  [string]$Database = $env:MONGODB_DB_NAME,
  [string]$BackupRoot = "./backups"
)

if (-not $MongoUri) { throw "Set MONGODB_BACKUP_URI before running backup." }
if (-not $Database) { $Database = "attendance_agent" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$target = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

mongodump --uri="$MongoUri" --db="$Database" --out="$target"
if ($LASTEXITCODE -ne 0) { throw "mongodump failed" }
Write-Host "MongoDB backup created at $target"
