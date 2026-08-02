#requires -Version 5.1
<#
.SYNOPSIS
  Collect a privacy-safe Hyperlab Windows workshop evidence bundle.

.DESCRIPTION
  Run inside the Windows workshop VM as Administrator after drivers, QEMU Guest
  Agent, Looking Glass host and the virtual display are configured. The script
  emits booleans, versions and counts only: no user names, email addresses,
  credentials, recovery keys or absolute profile paths.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("win11clean", "win11dirty")]
    [string]$Image,

    [Parameter(Mandatory = $true)]
    [ValidateSet("personal-singleton", "generalized-local-template")]
    [string]$IdentityMode,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^B[0-9]+-[0-9]+-g[0-9a-f]{10}$')]
    [string]$LookingGlassBuild,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$LookingGlassLog,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputPath,

    [switch]$Generalized,
    [switch]$MicrosoftAccountPresent,
    [switch]$LocalLabAccountPresent,
    [switch]$NoCredentialReuse
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Image -eq "win11clean") {
    if ($IdentityMode -ne "personal-singleton" -or $Generalized -or -not $MicrosoftAccountPresent) {
        throw "win11clean requires personal-singleton, Microsoft-account evidence and no generalized flag."
    }
}
else {
    if ($IdentityMode -ne "generalized-local-template" -or -not $Generalized -or $MicrosoftAccountPresent -or -not $LocalLabAccountPresent) {
        throw "win11dirty requires generalized-local-template, a local lab account and no Microsoft account."
    }
}
if (-not $NoCredentialReuse) {
    throw "Pass -NoCredentialReuse only after confirming that no credential was reused."
}
if (-not (Test-Path -LiteralPath $LookingGlassLog -PathType Leaf)) {
    throw "Looking Glass log does not exist: $LookingGlassLog"
}

function Test-RegistryPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [bool](Test-Path -LiteralPath $Path)
}

function Test-DevicePattern {
    param(
        [Parameter(Mandatory = $true)][object[]]$Devices,
        [Parameter(Mandatory = $true)][string]$Pattern
    )
    return [bool]($Devices | Where-Object {
        $_.ConfigManagerErrorCode -eq 0 -and $_.Name -match $Pattern
    } | Select-Object -First 1)
}

$secureBoot = $false
try {
    $secureBoot = [bool](Confirm-SecureBootUEFI)
}
catch {
    $secureBoot = $false
}

$tpmPresent = $false
$tpmReady = $false
$tpmSpecVersion = ""
try {
    $tpm = Get-Tpm
    $tpmPresent = [bool]$tpm.TpmPresent
    $tpmReady = [bool]$tpm.TpmReady
    $tpmSpecVersion = [string]$tpm.SpecVersion
}
catch {
    $tpmPresent = $false
    $tpmReady = $false
}

$qga = Get-Service -Name "qemu-ga" -ErrorAction SilentlyContinue
$lookingGlassService = Get-Service -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match 'Looking.*Glass' -or $_.DisplayName -match 'Looking.*Glass'
} | Select-Object -First 1

$devices = @(Get-CimInstance -ClassName Win32_PnPEntity | Select-Object Name, ConfigManagerErrorCode)
$video = @(Get-CimInstance -ClassName Win32_VideoController | Select-Object Name, CurrentHorizontalResolution, CurrentVerticalResolution, Status)

$nvidiaPresent = Test-DevicePattern -Devices $devices -Pattern 'NVIDIA'
$recoveryDisplayPresent = [bool]($video | Where-Object {
    $_.Name -notmatch 'NVIDIA' -and $_.Status -eq 'OK'
} | Select-Object -First 1)
$virtioInputPresent = Test-DevicePattern -Devices $devices -Pattern 'VirtIO.*Input|Red Hat.*Input'
$ivshmemPresent = Test-DevicePattern -Devices $devices -Pattern 'IVSHMEM|Inter-VM shared memory|Looking Glass'

$virtualDisplay = $video | Where-Object {
    $_.Name -match 'Virtual|Parsec|Indirect|IDD|IddSample'
} | Sort-Object -Property @{Expression = {
    [int64]$_.CurrentHorizontalResolution * [int64]$_.CurrentVerticalResolution
}; Descending = $true} | Select-Object -First 1

$virtualDisplayPresent = $null -ne $virtualDisplay
$virtualDisplayActive = $virtualDisplayPresent -and
    [int]$virtualDisplay.CurrentHorizontalResolution -gt 0 -and
    [int]$virtualDisplay.CurrentVerticalResolution -gt 0 -and
    $virtualDisplay.Status -eq 'OK'
$width = if ($virtualDisplayPresent) { [int]$virtualDisplay.CurrentHorizontalResolution } else { 0 }
$height = if ($virtualDisplayPresent) { [int]$virtualDisplay.CurrentVerticalResolution } else { 0 }

$lookingGlassLogText = Get-Content -LiteralPath $LookingGlassLog -Raw
$captureStarted = $lookingGlassLogText -match '====\s*\[\s*Capture Start\s*\]\s*===='
$captureInterface = ""
$interfaceMatch = [regex]::Match($lookingGlassLogText, '(?m)^\s*Using\s*:\s*(\S+)\s*$')
if ($interfaceMatch.Success) {
    $captureInterface = $interfaceMatch.Groups[1].Value
}

$rebootPending =
    (Test-RegistryPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
    (Test-RegistryPath 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\PendingFileRenameOperations')
$updateRebootPending = Test-RegistryPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'

$sysprepState = $null
try {
    $sysprepState = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\Setup\Status\SysprepStatus' -Name GeneralizationState -ErrorAction Stop).GeneralizationState
}
catch {
    $sysprepState = $null
}

$setupImageState = ""
try {
    $setupImageState = [string](Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Setup\State' -Name ImageState -ErrorAction Stop).ImageState
}
catch {
    $setupImageState = ""
}

if ($Image -eq "win11clean" -and $setupImageState -ne "IMAGE_STATE_COMPLETE") {
    throw "win11clean requires Windows Setup state IMAGE_STATE_COMPLETE; observed '$setupImageState'."
}
if ($Image -eq "win11dirty" -and $setupImageState -ne "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE") {
    throw "win11dirty must be collected after Sysprep /generalize /oobe /quit; observed '$setupImageState'."
}

$os = Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
$evidence = [ordered]@{
    schema_version = 1
    image = $Image
    collected_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    collector = [ordered]@{
        version = 1
        powershell = $PSVersionTable.PSVersion.ToString()
    }
    windows = [ordered]@{
        product = [string]$os.Caption
        version = [string]$os.Version
        build = [string]$os.BuildNumber
    }
    identity = [ordered]@{
        mode = $IdentityMode
        generalized = [bool]$Generalized
        microsoft_account_present = [bool]$MicrosoftAccountPresent
        local_lab_account_present = [bool]$LocalLabAccountPresent
        credential_reuse = $false
        sysprep_generalization_state = $sysprepState
        setup_image_state = $setupImageState
    }
    firmware = [ordered]@{
        secure_boot = $secureBoot
        tpm2_present = $tpmPresent -and $tpmSpecVersion -match '2\.0'
        tpm2_ready = $tpmReady
        tpm_spec_version = $tpmSpecVersion
    }
    drivers = [ordered]@{
        nvidia_gpu = $nvidiaPresent
        emulated_gpu_recovery = $recoveryDisplayPresent
        virtio_input = $virtioInputPresent
        ivshmem = $ivshmemPresent
    }
    services = [ordered]@{
        qemu_guest_agent = if ($null -ne $qga -and $qga.Status -eq 'Running') { 'running' } else { 'not-running' }
        looking_glass_host = if ($null -ne $lookingGlassService -and $lookingGlassService.Status -eq 'Running') { 'running' } else { 'not-running' }
    }
    looking_glass = [ordered]@{
        build = $LookingGlassBuild
        capture_started = $captureStarted
        capture_interface = $captureInterface
        log_basename = [System.IO.Path]::GetFileName($LookingGlassLog)
    }
    virtual_display = [ordered]@{
        present = $virtualDisplayPresent
        active = $virtualDisplayActive
        width = $width
        height = $height
    }
    hygiene = [ordered]@{
        reboot_pending = [bool]$rebootPending
        update_reboot_pending = [bool]$updateRebootPending
    }
}

$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($outputFullPath)
if (-not [string]::IsNullOrWhiteSpace($outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}
$evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outputFullPath -Encoding UTF8
Write-Host "Hyperlab workshop evidence written to $outputFullPath"
