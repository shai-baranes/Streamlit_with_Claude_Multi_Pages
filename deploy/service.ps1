param(
    [ValidateSet('install','start','stop','uninstall','status')][string]$Action = 'status',
    [string]$Python = '',
    [int]$Port = 8501
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$Wrapper = Join-Path $PSScriptRoot 'EngineeringDashboard.exe'
if (!(Test-Path $Wrapper)) { throw 'Place the official WinSW 2.x executable at deploy\EngineeringDashboard.exe first. See README_GPT.md.' }
if ($Action -eq 'install') {
    if (!$Python) { $Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
    if (!(Test-Path $Python)) { throw "Python executable not found: $Python" }
    $Template = Get-Content (Join-Path $PSScriptRoot 'service.xml.template') -Raw
    $Template.Replace('@PYTHON@', [Security.SecurityElement]::Escape($Python)).Replace('@ROOT@', [Security.SecurityElement]::Escape($ProjectRoot)).Replace('@PORT@', "$Port") | Set-Content (Join-Path $PSScriptRoot 'EngineeringDashboard.xml') -Encoding UTF8
}
& $Wrapper $Action
if ($LASTEXITCODE -ne 0) { throw "WinSW $Action failed ($LASTEXITCODE)" }
