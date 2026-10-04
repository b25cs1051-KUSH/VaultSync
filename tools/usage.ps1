# Shared helper: estimated USD-equivalent usage of this machine's active 5-hour block,
# as reported by the local BAND daemon. Returns $null when it cannot be read.
function Find-CostValue($node) {
    if ($null -eq $node) { return $null }
    if ($node -is [System.Array]) {
        foreach ($n in $node) { $v = Find-CostValue $n; if ($null -ne $v) { return $v } }
        return $null
    }
    if ($node -is [System.Management.Automation.PSCustomObject]) {
        foreach ($p in $node.PSObject.Properties) {
            if ($p.Name -match 'cost|usd|equivalent' -and $p.Name -notmatch 'burn|rate|proj|hour' -and $p.Value -is [ValueType]) {
                return [double]$p.Value
            }
        }
        foreach ($p in $node.PSObject.Properties) { $v = Find-CostValue $p.Value; if ($null -ne $v) { return $v } }
    }
    return $null
}

function Get-BlockUsd {
    param([string]$BandExe = "$env:LOCALAPPDATA\Band\band.exe")
    if (-not (Test-Path $BandExe)) { return $null }
    $raw = (& $BandExe usage blocks --active --json 2>$null) -join "`n"
    if ($raw) {
        try {
            $b = $raw | ConvertFrom-Json
            # BAND's own price catalog can be missing for a model (it then reports 0), so weight the
            # token counts with one fixed set of per-million rates. Limits are calibrated in the same unit.
            if ($null -ne $b.cacheReadTokens) {
                return [math]::Round(($b.inputTokens * 5 + $b.outputTokens * 25 + $b.cacheCreationTokens * 6.25 + $b.cacheReadTokens * 0.5) / 1e6, 2)
            }
            $v = Find-CostValue $b; if ($null -ne $v) { return [math]::Round($v, 2) }
        } catch { }
    }
    $text = (& $BandExe usage blocks --active 2>$null) -join "`n"
    if ($text -match '\$\s?([0-9]+(\.[0-9]+)?)') { return [double]$Matches[1] }
    if ($text -match '\(no active block\)') { return 0.0 }
    return $null
}
