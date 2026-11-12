$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiProject = Join-Path $projectRoot "backend\DailyWork.Api\DailyWork.Api.csproj"

Write-Host ""
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host " DailyWork - Brevo SMTP setup" -ForegroundColor Cyan
Write-Host "=============================================================" -ForegroundColor Cyan
Write-Host "Use the SMTP login and SMTP key from Brevo, NOT your Brevo"
Write-Host "account password and NOT a Brevo API key."
Write-Host "Find them at: Brevo > Settings > SMTP & API > SMTP"
Write-Host ""

$login = (Read-Host "Enter your Brevo SMTP login").Trim()
if ([string]::IsNullOrWhiteSpace($login)) {
    throw "Brevo SMTP login is required."
}

$sender = (Read-Host "Enter your VERIFIED sender email address").Trim()
if ($sender -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
    throw "Please enter a valid verified sender email address."
}

$secureKey = Read-Host "Paste your Brevo SMTP key (input is hidden)" -AsSecureString
$ptr = [IntPtr]::Zero
$smtpKey = $null

try {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $smtpKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $smtpKey = $smtpKey.Trim()

    if ([string]::IsNullOrWhiteSpace($smtpKey)) {
        throw "Brevo SMTP key cannot be empty."
    }

    # Process-scoped only. Credentials are not written to project files.
    $env:Smtp__Host = "smtp-relay.brevo.com"
    $env:Smtp__Port = "587"
    $env:Smtp__Username = $login
    $env:Smtp__Password = $smtpKey
    $env:Smtp__EnableSsl = "true"
    $env:Smtp__From = $sender
    $env:Smtp__FromName = "DailyWork"
    $env:Smtp__OutboxFolder = "email-outbox"
    $env:Smtp__SiteUrl = "http://localhost:5000"

    Write-Host ""
    Write-Host "Brevo SMTP settings loaded for this run." -ForegroundColor Green
    Write-Host "SMTP host: smtp-relay.brevo.com"
    Write-Host "SMTP port: 587 (STARTTLS)"
    Write-Host "Verified sender: $sender"
    Write-Host "Starting DailyWork. Keep this window open."
    Write-Host "Look for 'Email: sending through smtp-relay.brevo.com' at startup."
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
    $smtpKey = $null
    $secureKey = $null
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
