@echo off
setlocal DisableDelayedExpansion
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if not "%~4"=="" goto usage
if /i "%~2"=="--stop-all" if not "%~3"=="" goto usage
set "DASHBOARD_CLIENT_WRAPPER=1"
set "DASHBOARD_CLIENT_SCRIPT=%~dp0client_load_csv.ps1"
set "DASHBOARD_CLIENT_URL=%~1"
set "DASHBOARD_CLIENT_FILE=%~2"
set "DASHBOARD_CLIENT_PARQUET=%~3"
rem Run the policy check in the same PowerShell process that will invoke the script.
powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop'; $script = $env:DASHBOARD_CLIENT_SCRIPT; $p = $env:DASHBOARD_CLIENT_PARQUET;" ^
    "if ($p -and $p -notin @('true','false')) { [Console]::Error.WriteLine('Parquet must be true or false.'); exit 2 };" ^
    "try {" ^
    "    if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Place client_load_csv.ps1 next to this CMD launcher.' };" ^
    "    if ((Get-ExecutionPolicy) -eq 'RemoteSigned' -and (Get-Item -LiteralPath $script -Stream Zone.Identifier -ErrorAction SilentlyContinue) -and (Get-AuthenticodeSignature -LiteralPath $script).Status -eq 'NotSigned') {" ^
    "        Write-Host ('Downloaded PowerShell script: ' + $script);" ^
    "        Write-Host 'Review the file and confirm your organization permits unblocking it.';" ^
    "        if ((Read-Host 'Remove the download marker from this file and run it? [y/N]') -ne 'y') { exit 1 };" ^
    "        Unblock-File -LiteralPath $script;" ^
    "    };" ^
    "    if ($env:DASHBOARD_CLIENT_FILE -eq '--stop-all') { & $script -ServerUrl $env:DASHBOARD_CLIENT_URL -StopAll } else { & $script -ServerUrl $env:DASHBOARD_CLIENT_URL -CsvFile $env:DASHBOARD_CLIENT_FILE -Parquet ($p -eq 'true') };" ^
    "    if (-not $?) { exit 1 }; exit 0;" ^
    "} catch [System.Management.Automation.PSSecurityException] {" ^
    "    [Console]::Error.WriteLine($_.Exception.Message);" ^
    "    Get-ExecutionPolicy -List | Out-Host;" ^
    "    [Console]::Error.WriteLine('Ask your administrator about approved script execution, or use the dashboard Upload button.'); exit 1;" ^
    "} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
exit /b %ERRORLEVEL%
:usage
echo Usage: client_load_csv.cmd SERVER_URL CSV_PATH [true^|false] >&2
echo        client_load_csv.cmd SERVER_URL --stop-all >&2
exit /b 2
