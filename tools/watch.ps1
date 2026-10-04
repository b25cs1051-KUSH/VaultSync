<#
Factory watchdog. Waits until something needs the Architect's attention, then prints one line.
  ALERT USAGE <account> <85|95>%  this account's 5-hour block crossed a warning level
  ALERT RESUME <account>          the window reset after the account reached the top level
  ALERT SILENCE                   no commit and no local seat activity for silence_minutes
  MESSAGE                         a message is queued for the given seat
  TIMEOUT                         nothing to report for -Minutes minutes
Claude usage is read from this machine's BAND daemon. Other accounts are read from the
"Usage-Block: <harness> <usd>" trailer that tools/commit.ps1 adds to every commit.
Limits live in tools/factory-limits.json (a block size of 0 disables that account's alerts).
-CheckHeartbeat prints OK or STALE (no watch loop has run for 15 minutes) and exits.
#>
param(
    [string]$Seat = "",
    [int]$Minutes = 9,
    [int]$IntervalSeconds = 30,
    [string]$Branch = "main",
    [string]$IgnoreScope = "watchdog",
    [string]$BandExe = "$env:LOCALAPPDATA\Band\band.exe",
    [switch]$CheckHeartbeat
)
. "$PSScriptRoot\usage.ps1"

$stateDir = Join-Path $env:TEMP "factory-watch"
New-Item -ItemType Directory -Force $stateDir | Out-Null
$heartbeat = Join-Path $stateDir "heartbeat.txt"
$stateFile = Join-Path $stateDir "state.json"

if ($CheckHeartbeat) {
    if ((Test-Path $heartbeat) -and ((Get-Date) - (Get-Item $heartbeat).LastWriteTime).TotalMinutes -lt 15) { "OK" } else { "STALE" }
    exit 0
}
if (-not $Seat) { Write-Output "ERROR: -Seat is required"; exit 1 }

$limits = Get-Content (Join-Path $PSScriptRoot "factory-limits.json") -Raw | ConvertFrom-Json
# Optional: watch a clone other than the current directory.
if ($limits.PSObject.Properties.Name -contains "repo_dir" -and $limits.repo_dir) { Set-Location $limits.repo_dir }
$levels = @($limits.warn_percent | Sort-Object -Descending)
$state = @{ Claude = @{ level = 0; usd = 0 }; Codex = @{ level = 0; usd = 0 }; silenceAt = "" }
if (Test-Path $stateFile) {
    try {
        $s = Get-Content $stateFile -Raw | ConvertFrom-Json
        $state.Claude = @{ level = [int]$s.Claude.level; usd = [double]$s.Claude.usd }
        $state.Codex = @{ level = [int]$s.Codex.level; usd = [double]$s.Codex.usd }
        $state.silenceAt = [string]$s.silenceAt
    } catch { }
}
function Save-State { $state | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $stateFile }

function Test-Usage($account, $usd, $cap) {
    if ($null -eq $usd -or $cap -le 0) { return $null }
    # A new 5-hour block starts lower: forget earlier warnings. If the account had reached the
    # top level (the stage stopped for usage), tell the Architect it can resume.
    if ($usd + 0.5 -lt $state[$account].usd) {
        $wasBlocked = $state[$account].level -ge $levels[0]
        $state[$account].level = 0
        $state[$account].usd = $usd
        if ($wasBlocked) { return "ALERT RESUME $account - the 5-hour usage window has reset" }
    }
    $state[$account].usd = $usd
    $pct = [math]::Round(100 * $usd / $cap)
    foreach ($l in $levels) {
        if ($pct -ge $l -and $state[$account].level -lt $l) {
            $state[$account].level = $l
            return "ALERT USAGE $account $l% - about `$$usd of `$$cap in the current 5-hour block"
        }
    }
    return $null
}

function Get-CodexUsd {
    $lines = git log "origin/$Branch" -n 50 --since="5 hours ago" --format="%(trailers:key=Usage-Block,valueonly)" 2>$null
    foreach ($l in $lines) { if ($l -match '^\s*Codex\s+([0-9.]+)\s*$') { return [double]$Matches[1] } }
    return $null
}

function Get-LastActivityMinutes {
    $times = @()
    $c = git log "origin/$Branch" -1 --format=%ct 2>$null
    if ($c) { $times += [DateTimeOffset]::FromUnixTimeSeconds([int64]$c).LocalDateTime }
    if (Test-Path $BandExe) {
        $a = & $BandExe activity list 2>$null | Where-Object { $_ -notmatch $IgnoreScope } | Select-Object -First 1
        if ($a -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})') { $times += [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm', $null) }
    }
    if ($times.Count -eq 0) { return 0 }
    return ((Get-Date) - ($times | Sort-Object -Descending | Select-Object -First 1)).TotalMinutes
}

$deadline = (Get-Date).AddMinutes($Minutes)
while ($true) {
    Set-Content -Encoding utf8 $heartbeat (Get-Date -Format o)
    if (Test-Path $BandExe) {
        # Report only messages not seen before: BAND can keep an already-handled message queued.
        $ids = @(& $BandExe inbox --as $Seat 2>$null | Where-Object { $_ -match '^\[[^\]]+\]\s+(\S+)' } | ForEach-Object { ($_ -split '\s+')[1] })
        $seenFile = Join-Path $stateDir "seen-messages.txt"
        $seen = if (Test-Path $seenFile) { @(Get-Content $seenFile) } else { @() }
        $new = @($ids | Where-Object { $seen -notcontains $_ })
        if ($new.Count -gt 0) {
            Add-Content -Encoding utf8 $seenFile $new
            Write-Output "MESSAGE: $($new.Count) new message(s) for $Seat. Read them now."; Save-State; exit 0
        }
    }
    git fetch --quiet origin $Branch 2>$null | Out-Null
    # BAND's usage archive is only current after a refresh; refresh at most every 5 minutes.
    $refreshFile = Join-Path $stateDir "refreshed.txt"
    if (-not (Test-Path $refreshFile) -or ((Get-Date) - (Get-Item $refreshFile).LastWriteTime).TotalMinutes -ge 5) {
        & $BandExe usage refresh 2>$null | Out-Null
        Set-Content -Encoding utf8 $refreshFile (Get-Date -Format o)
    }
    foreach ($alert in @((Test-Usage "Claude" (Get-BlockUsd -BandExe $BandExe) $limits.claude_block_usd), (Test-Usage "Codex" (Get-CodexUsd) $limits.codex_block_usd))) {
        if ($alert) { Write-Output $alert; Save-State; exit 0 }
    }
    $idle = Get-LastActivityMinutes
    $sinceAlert = if ($state.silenceAt) { ((Get-Date) - [datetime]$state.silenceAt).TotalMinutes } else { [double]::MaxValue }
    # While an account sits at the top usage level the stage is stopped on purpose: no silence alerts.
    $blocked = ($state.Claude.level -ge $levels[0]) -or ($state.Codex.level -ge $levels[0])
    if (-not $blocked -and $idle -ge $limits.silence_minutes -and $sinceAlert -ge $limits.silence_minutes) {
        $state.silenceAt = (Get-Date -Format o)
        Write-Output "ALERT SILENCE - no commit and no seat activity for $([math]::Round($idle)) minutes"
        Save-State; exit 0
    }
    if ((Get-Date) -ge $deadline) { Write-Output "TIMEOUT: nothing to report for $Minutes minutes."; Save-State; exit 0 }
    Start-Sleep -Seconds $IntervalSeconds
}
