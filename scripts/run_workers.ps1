$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\backend')
if (-not $env:WORKER_CONSUMER_NAME) { $env:WORKER_CONSUMER_NAME = "attendance-worker-$env:COMPUTERNAME" }
if (-not $env:NOTIFICATION_CONSUMER_NAME) { $env:NOTIFICATION_CONSUMER_NAME = "notification-worker-$env:COMPUTERNAME" }
Start-Process powershell -ArgumentList '-NoExit','-Command','python -m app.worker'
Start-Process powershell -ArgumentList '-NoExit','-Command','python -m app.notification_worker'
