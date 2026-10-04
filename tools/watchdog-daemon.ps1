<#
Watchdog daemon: runs the watch loop without a model, so it costs no tokens and keeps running
when a usage limit stops every model seat. It posts each ALERT to the Architect as the Watchdog
seat, and stays quiet while the Architect has the Watchdog stopped.
Configuration (machine-local, not committed): tools/watchdog.local.json
  { "room_id": "...", "architect": "owner/handle", "watchdog": "owner/handle",
    "watchdog_id": "<participant id>", "repo_dir": "<clone of the run repository>" }
Start: Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','<path>\tools\watchdog-daemon.ps1'
#>
param([string]$BandExe = "$env:LOCALAPPDATA\Band\band.exe")
$cfgFile = Join-Path $PSScriptRoot "watchdog.local.json"
$log = Join-Path $env:TEMP "factory-watch\daemon.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

function Write-Log($m) { Add-Content -Encoding utf8 $log "$(Get-Date -Format s) $m" }

# The Architect controls the Watchdog with START and STOP; the newest of the two wins.
function Test-Stopped($cfg) {
    $lines = & $BandExe room messages $cfg.room_id 2>$null | Where-Object { $_ -match '\[text\]' -and $_ -match [regex]::Escape($cfg.watchdog_id) -and $_ -match '\b(START|STOP)\b' }
    $last = $lines | Select-Object -Last 1
    return ($last -match '\bSTOP\b')
}

Write-Log "daemon started"
while ($true) {
    try {
        $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
        if (Test-Stopped $cfg) { Start-Sleep -Seconds 60; continue }
        Push-Location $cfg.repo_dir
        git pull -q --ff-only 2>$null | Out-Null
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "watch.ps1") -Seat none
        Pop-Location
        $alert = $out | Where-Object { $_ -match '^ALERT' } | Select-Object -First 1
        if ($alert) {
            & $BandExe send --as $cfg.watchdog $cfg.room_id "@$($cfg.architect) $alert" | Out-Null
            Write-Log "posted: $alert"
        }
    } catch { Write-Log "error: $_"; Start-Sleep -Seconds 60 }
}
