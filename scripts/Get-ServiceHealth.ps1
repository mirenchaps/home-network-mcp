<#
.SYNOPSIS
    Checks the status of one or more Windows services on a target host.

.DESCRIPTION
    Queries service state (Running/Stopped/etc.) either locally or against a
    remote host over WinRM. Returns JSON so the MCP server can parse it directly.

.PARAMETER ComputerName
    Target host. Defaults to localhost. Use a remote hostname for home lab VMs.

.PARAMETER ServiceNames
    One or more service names to check, e.g. "Spooler","W32Time"

.EXAMPLE
    ./Get-ServiceHealth.ps1 -ComputerName "HOMELAB-DC01" -ServiceNames "DNS","NTDS"
#>

param(
    [string]$ComputerName = "localhost",

    [Parameter(Mandatory = $true)]
    [string[]]$ServiceNames,

    [string]$Username = "",
    [string]$Password = ""
)

$ErrorActionPreference = "Stop"

try {
    if ($ComputerName -eq "localhost" -or $ComputerName -eq $env:COMPUTERNAME) {
        $services = Get-Service -Name $ServiceNames -ErrorAction SilentlyContinue
    } else {
        $invokeParams = @{
            ComputerName = $ComputerName
            ScriptBlock  = { param($names) Get-Service -Name $names -ErrorAction SilentlyContinue }
            ArgumentList = (,$ServiceNames)
        }
        if ($Username -and $Password) {
            $securePass = ConvertTo-SecureString $Password -AsPlainText -Force
            $invokeParams.Credential      = New-Object PSCredential($Username, $securePass)
            $invokeParams.Authentication  = "Basic"
            $invokeParams.UseSSL          = $true
            $invokeParams.Port            = 5986
            $invokeParams.SessionOption   = New-PSSessionOption -OperationTimeout 10000
        }
        $services = Invoke-Command @invokeParams
    }

    $results = foreach ($svc in $services) {
        [PSCustomObject]@{
            name         = $svc.Name
            display_name = $svc.DisplayName
            status       = $svc.Status.ToString()
            start_type   = $svc.StartType.ToString()
        }
    }

    $output = [PSCustomObject]@{
        computer     = $ComputerName
        checked_at   = (Get-Date).ToString("o")
        services     = @($results)
        error        = $null
    }
}
catch {
    $output = [PSCustomObject]@{
        computer   = $ComputerName
        checked_at = (Get-Date).ToString("o")
        services   = @()
        error      = $_.Exception.Message
    }
}

$output | ConvertTo-Json -Depth 4
