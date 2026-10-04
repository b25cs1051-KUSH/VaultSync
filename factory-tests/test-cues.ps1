<#
Failure-test conductor. Watches the test repository and posts a TEST CUE in the room,
mentioning the human who must act, when each failure should be injected. It never
mentions a seat, so no agent is woken by it, and it spends no model tokens.
T5 is injected automatically: it lowers the Claude block size in the Watchdog's local
copy of tools/factory-limits.json so current usage reads as about 90% and the 85% alert fires.
#>
param(
    [string]$Repo = "https://github.com/b25cs1051-KUSH/Vsultsync-scratch.git",
    [string]$Room = "029f4041-3777-43a3-8ac4-fff117d82fad",
    [string]$Kush = "0f08e863-8c86-4c63-a4a4-d59da016587e",
    [string]$Jatin = "1af918df-e55b-4e49-a44e-fb56031d50b1",
    [string]$WatchdogLimits = "E:\run-watchdog\tools\factory-limits.json",
    [string]$WorkDir = "E:\factory-runs\cues",
    [string]$BandExe = "$env:LOCALAPPDATA\Band\band.exe"
)

function Send-Cue($who, $text) {
    & $BandExe room send $Room "TEST CUE $text" --mention $who | Out-Null
    Write-Output "$(Get-Date -Format HH:mm) $text"
}

if (-not (Test-Path $WorkDir)) { git clone -q $Repo $WorkDir }
Set-Location $WorkDir
Send-Cue $Jatin "T1 - test started. Humans do nothing until the next cue."

$step = 2
while ($step -le 6) {
    Start-Sleep -Seconds 30
    git pull -q --rebase origin main 2>$null | Out-Null
    $log = @(git log --reverse --format="%an|%s" 2>$null)
    $authors = $log | ForEach-Object { ($_ -split '\|', 2)[0] }
    $passes = @($log | Where-Object { $_ -match '^Verifier\|.*PASS' }).Count
    $firstPass = [array]::FindIndex([string[]]$log, [Predicate[string]]{ param($l) $l -match '^Verifier\|.*PASS' })

    if ($step -eq 2 -and $firstPass -ge 0) {
        $after = $log[($firstPass + 1)..($log.Count)] | Where-Object { $_ -match '^Builder\|' }
        if ($after) { Send-Cue $Jatin "T2 - Jatin: quit BAND Desktop now (tray icon too). Keep it closed until the T3 cue."; $step = 3 }
    }
    elseif ($step -eq 3 -and ($authors -contains 'Reserve Builder' -or $authors -contains 'Reserve Breaker')) {
        Send-Cue $Jatin "T3 - failover happened. Jatin: reopen BAND Desktop now."; $step = 4
    }
    elseif ($step -eq 4 -and ($log | Where-Object { $_ -match '^Reserve Breaker\|' })) {
        Send-Cue $Jatin "T4 - Kush: quit Docker Desktop now, start it again after 2 minutes."; $step = 5
    }
    elseif ($step -eq 5 -and $passes -ge 2) {
        if (Test-Path $WatchdogLimits) {
            $l = Get-Content $WatchdogLimits -Raw | ConvertFrom-Json
            . "$WorkDir\tools\usage.ps1"
            $now = Get-BlockUsd -BandExe $BandExe
            if ($null -eq $now) { $now = 1 }
            $l.claude_block_usd = [math]::Round($now / 0.9, 2)   # current usage now reads as about 90%
            $l | ConvertTo-Json | Set-Content -Encoding utf8 $WatchdogLimits
            Send-Cue $Jatin "T5 - Claude usage limit lowered for the Watchdog. Expect ALERT USAGE Claude. Humans do nothing."
        } else {
            Send-Cue $Jatin "T5 - could not find $WatchdogLimits. Ask Claude Code to inject T5."
        }
        $step = 6
    }
    elseif ($step -eq 6 -and (Test-Path "handoffs/architect")) {
        Send-Cue $Jatin "T6 - final report is in. Humans do nothing for 15 minutes. Test conductor stopping."; $step = 7
    }
}
