<#
.SYNOPSIS
    Sweeps a subnet and reports which devices are online, with basic latency info.

.DESCRIPTION
    Given a subnet prefix (e.g. "192.168.1"), pings hosts 1-254 in parallel and
    returns JSON describing which are alive. Designed to be called from the MCP
    server via subprocess, so output is JSON-only on stdout.

.PARAMETER Subnet
    The first three octets of the subnet, e.g. "192.168.1"

.PARAMETER StartHost / EndHost
    Range of host octets to scan (default 1-254)

.EXAMPLE
    ./Get-DeviceStatus.ps1 -Subnet "192.168.1"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Subnet,

    [int]$StartHost = 1,
    [int]$EndHost = 254,

    [int]$TimeoutMs = 500
)

$ErrorActionPreference = "SilentlyContinue"

$results = (($StartHost..$EndHost) | ForEach-Object -Parallel {
    $ip = "$($using:Subnet).$_"
    $ping = New-Object System.Net.NetworkInformation.Ping
    try {
        $reply = $ping.Send($ip, $using:TimeoutMs)
        if ($reply.Status -eq "Success") {
            [PSCustomObject]@{
                ip            = $ip
                online        = $true
                latency_ms    = $reply.RoundtripTime
            }
        }
    } catch {
        # host unreachable, skip
    }
} -ThrottleLimit 64)

$output = [PSCustomObject]@{
    subnet       = $Subnet
    scanned_at   = (Get-Date).ToString("o")
    devices_up   = @($results)
    device_count = @($results).Count
}

$output | ConvertTo-Json -Depth 4
