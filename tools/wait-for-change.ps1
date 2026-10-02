<#
Factory watchdog: wait until something needs the lead seat's attention.

Returns as soon as one of these happens, then prints one short result block:
  MESSAGE  - a message is queued for the given seat in BAND
  COMMIT   - the shared branch on the remote has a new commit
  TIMEOUT  - nothing changed for -Minutes minutes

It never posts anything and never changes the repository. While it waits, no model
tokens are spent. The result block ends with the latest commit per author, so the
lead seat can see who has been silent.

Usage (from inside a clone of the shared repository):
  powershell -NoProfile -ExecutionPolicy Bypass -File tools/wait-for-change.ps1 -Seat <owner/handle>
Run it with a tool timeout longer than -Minutes (default 9).
#>
param(
    [Parameter(Mandatory = $true)][string]$Seat,
    [int]$Minutes = 9,
    [int]$IntervalSeconds = 30,
    [string]$Branch = "main",
    [string]$BandExe = "$env:LOCALAPPDATA\Band\band.exe"
)

function Get-RemoteHead {
    $line = git ls-remote origin "refs/heads/$Branch" 2>$null | Select-Object -First 1
    if ($line) { return ($line -split "\s+")[0] } else { return "" }
}

function Get-QueuedCount {
    if (-not (Test-Path $BandExe)) { return 0 }
    $out = & $BandExe inbox --as $Seat 2>$null
    return @($out | Where-Object { $_ -match '^\[' }).Count
}

function Write-Activity {
    git fetch --quiet origin $Branch 2>$null | Out-Null
    Write-Output "Latest commit per author on origin/${Branch}:"
    git log "origin/$Branch" -n 200 --format="%an|%ar|%h %s" 2>$null |
        Group-Object { ($_ -split '\|')[0] } |
        ForEach-Object { "  " + ($_.Group[0] -replace '\|', ' | ') }
}

$startHead = Get-RemoteHead
$deadline = (Get-Date).AddMinutes($Minutes)

while ((Get-Date) -lt $deadline) {
    $queued = Get-QueuedCount
    if ($queued -gt 0) {
        Write-Output "MESSAGE: $queued message(s) queued for $Seat. Read them now."
        exit 0
    }
    $head = Get-RemoteHead
    if ($head -and $startHead -and $head -ne $startHead) {
        Write-Output "COMMIT: origin/$Branch moved from $($startHead.Substring(0,7)) to $($head.Substring(0,7))."
        Write-Activity
        exit 0
    }
    Start-Sleep -Seconds $IntervalSeconds
}

Write-Output "TIMEOUT: no new message or commit for $Minutes minutes."
Write-Activity
exit 0
