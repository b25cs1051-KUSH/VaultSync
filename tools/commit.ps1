<#
Commit the staged changes under the seat's own identity and record this machine's
current 5-hour usage as a trailer, so the Watchdog can warn before an account runs out.
Usage: powershell -NoProfile -ExecutionPolicy Bypass -File tools/commit.ps1 -Seat "<seat name>" -Harness "<harness>" -Subject "<subject>"
#>
param(
    [Parameter(Mandatory = $true)][string]$Seat,
    [Parameter(Mandatory = $true)][string]$Harness,
    [Parameter(Mandatory = $true)][string]$Subject
)
. "$PSScriptRoot\usage.ps1"
$usd = Get-BlockUsd
if ($null -eq $usd) { $usd = "unknown" }
$email = ($Seat.ToLower() -replace '[^a-z0-9]+', '-') + "@factory.local"
git -c "user.name=$Seat" -c "user.email=$email" commit -m $Subject -m "Usage-Block: $Harness $usd"
exit $LASTEXITCODE
