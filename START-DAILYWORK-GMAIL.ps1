$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiProject = Join-Path $projectRoot "backend\DailyWork.Api\DailyWork.Api.csproj"

Write-Host ""
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host " DailyWork - Gmail email setup" -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host "Use a Gmail App Password, NOT your normal Google password."
Write-Host "Create one at: https://myaccount.google.com/apppasswords"
Write-Host ""

$gmail = (Read-Host "Enter the Gmail address used to send DailyWork emails").Trim()
if ($gmail -notmatch '^[^@\s]+@gmail\.com$') {
    throw "Please enter a valid @gmail.com sender address."
}

$securePassword = Read-Host "Paste the 16-character Gmail App Password (input is hidden)" -AsSecureString
$ptr = [IntPtr]::Zero
$appPassword = $null

try {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $appPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $appPassword = ($appPassword -replace '\s','')

    if ($appPassword.Length -ne 16) {
        throw "A Gmail App Password should contain 16 characters. Create a new App Password and try again."
    }

    # Process-scoped only. Nothing is written to appsettings.json or saved permanently.
    $env:Smtp__Host = "smtp.gmail.com"
    $env:Smtp__Port = "587"
    $env:Smtp__Username = $gmail
    $env:Smtp__Password = $appPassword
    $env:Smtp__EnableSsl = "true"
    $env:Smtp__From = $gmail
    $env:Smtp__FromName = "DailyWork"
    $env:Smtp__OutboxFolder = "email-outbox"
    $env:Smtp__SiteUrl = "http://localhost:5000"

    Write-Host ""
    Write-Host "Gmail SMTP settings loaded for this run." -ForegroundColor Green
    Write-Host "Sender: $gmail"
    Write-Host "Starting DailyWork. Keep this window open."
    Write-Host "Look for 'Email: sending through smtp.gmail.com' in the startup message."
    Write-Host ""

    Push-Location $projectRoot
    try {
        dotnet run --project $apiProject
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $appPassword = $null
    $securePassword = $null
    Remove-Item Env:Smtp__Password -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__Username -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__From -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__Host -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__Port -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__EnableSsl -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__FromName -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__OutboxFolder -ErrorAction SilentlyContinue
    Remove-Item Env:Smtp__SiteUrl -ErrorAction SilentlyContinue
}
