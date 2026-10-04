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
        try { $v = Find-CostValue ($raw | ConvertFrom-Json); if ($null -ne $v) { return [math]::Round($v, 2) } } catch { }
    }
    $text = (& $BandExe usage blocks --active 2>$null) -join "`n"
    if ($text -match '\$\s?([0-9]+(\.[0-9]+)?)') { return [double]$Matches[1] }
    return $null
}
