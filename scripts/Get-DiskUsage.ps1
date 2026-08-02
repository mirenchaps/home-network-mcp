<#
.SYNOPSIS
    Reports disk usage (free/used/total, percent free) for all fixed volumes on a host.

.PARAMETER ComputerName
    Target host. Defaults to localhost.

.PARAMETER WarnThresholdPercent
    Percent free space below which a volume is flagged as "warning" (default 15).

.EXAMPLE
    ./Get-DiskUsage.ps1 -ComputerName "HOMELAB-FILESRV"
#>

param(
    [string]$ComputerName = "localhost",
    [int]$WarnThresholdPercent = 15,
    [string]$Username = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

$scriptBlock = {
    param($warnThreshold)
    Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } | ForEach-Object {
        $percentFree = if ($_.Size -gt 0) { [math]::Round(($_.SizeRemaining / $_.Size) * 100, 1) } else { 0 }
        [PSCustomObject]@{
            drive           = "$($_.DriveLetter):"
            label           = $_.FileSystemLabel
            size_gb         = [math]::Round($_.Size / 1GB, 1)
            free_gb         = [math]::Round($_.SizeRemaining / 1GB, 1)
            percent_free    = $percentFree
            warning         = $percentFree -lt $warnThreshold
        }
    }
}

try {
    if ($ComputerName -eq "localhost" -or $ComputerName -eq $env:COMPUTERNAME) {
        $volumes = & $scriptBlock $WarnThresholdPercent
    } else {
        $invokeParams = @{
            ComputerName = $ComputerName
            ScriptBlock  = $scriptBlock
            ArgumentList = $WarnThresholdPercent
        }
        # On Linux, Kerberos is unavailable — pass explicit credentials if provided.
        if ($Username -and $Password) {
            $securePass = ConvertTo-SecureString $Password -AsPlainText -Force
            $invokeParams.Credential = New-Object PSCredential($Username, $securePass)
            $invokeParams.Authentication = "Basic"
        }
        $volumes = Invoke-Command @invokeParams
    }

    $output = [PSCustomObject]@{
        computer   = $ComputerName
        checked_at = (Get-Date).ToString("o")
        volumes    = @($volumes)
        error      = $null
    }
}
catch {
    $output = [PSCustomObject]@{
        computer   = $ComputerName
        checked_at = (Get-Date).ToString("o")
        volumes    = @()
        error      = $_.Exception.Message
    }
}

$output | ConvertTo-Json -Depth 4
