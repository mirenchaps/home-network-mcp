<#
.SYNOPSIS
    Returns system uptime and last boot time for a target host.

.PARAMETER ComputerName
    Target host. Defaults to localhost.

.EXAMPLE
    ./Get-SystemUptime.ps1 -ComputerName "HOMELAB-DC01"
#>

param(
    [string]$ComputerName = "localhost",
    [string]$Username = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

try {
    if ($ComputerName -eq "localhost" -or $ComputerName -eq $env:COMPUTERNAME) {
        $os = Get-CimInstance -ClassName Win32_OperatingSystem
    } else {
        # CimInstance doesn't take -UseSSL directly — we create an explicit
        # CimSession with SSL and pass that in instead.
        if ($Username -and $Password) {
            $securePass = ConvertTo-SecureString $Password -AsPlainText -Force
            $credential = New-Object PSCredential($Username, $securePass)
            $sessionOpts = New-CimSessionOption -UseSsl
            $session = New-CimSession `
                -ComputerName $ComputerName `
                -Port 5986 `
                -Credential $credential `
                -Authentication Basic `
                -SessionOption $sessionOpts
            $os = Get-CimInstance -ClassName Win32_OperatingSystem -CimSession $session
            Remove-CimSession $session
        } else {
            $os = Get-CimInstance -ClassName Win32_OperatingSystem -ComputerName $ComputerName
        }
    }

    $lastBoot = $os.LastBootUpTime
    $uptime   = (Get-Date) - $lastBoot

    $output = [PSCustomObject]@{
        computer        = $ComputerName
        checked_at      = (Get-Date).ToString("o")
        last_boot       = $lastBoot.ToString("o")
        uptime_days     = [math]::Round($uptime.TotalDays, 2)
        uptime_readable = "{0}d {1}h {2}m" -f $uptime.Days, $uptime.Hours, $uptime.Minutes
        error           = $null
    }
}
catch {
    $output = [PSCustomObject]@{
        computer   = $ComputerName
        checked_at = (Get-Date).ToString("o")
        error      = $_.Exception.Message
    }
}

$output | ConvertTo-Json -Depth 4
