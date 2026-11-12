[CmdletBinding(DefaultParameterSetName = 'Upload')]
param(
    [Parameter(Mandatory = $true)][string]$ServerUrl,
    [Parameter(Mandatory = $true, ParameterSetName = 'Upload')][string]$CsvFile,
    [Parameter(ParameterSetName = 'Upload')][bool]$Parquet = $false,
    [Parameter(Mandatory = $true, ParameterSetName = 'Stop')][switch]$StopAll
)

function Get-OriginShell {
    if ($env:DASHBOARD_CLIENT_WRAPPER -ne '1') {
        return Get-Process -Id $PID
    }

    # CMD may itself be a transient helper when called from PowerShell.
    $child = Get-CimInstance Win32_Process -Filter "ProcessId = $PID"
    for ($depth = 0; $depth -lt 16 -and $child; $depth++) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($child.ParentProcessId)"
        if (-not $parent -or $parent.CreationDate -gt $child.CreationDate) { break }
        if ($parent.Name -in @('cmd.exe', 'powershell.exe', 'pwsh.exe')) {
            if (-not $parent.CommandLine) { break }
            if ($parent.Name -ne 'cmd.exe' -or $parent.CommandLine -notmatch '(?i)(?:\s|")/c(?:\s|")') {
                $shell = Get-Process -Id $parent.ProcessId
                # WMI timestamps may have less precision than Get-Process.
                if ([Math]::Abs(($shell.StartTime - $parent.CreationDate).TotalSeconds) -lt 1) {
                    return $shell
                }
                break
            }
        }
        $child = $parent
    }
    throw 'Could not identify the originating terminal. Run the script from an interactive PowerShell or Command Prompt.'
}

function Get-ClientCredential([Uri]$Base, [bool]$Create) {
    $shell = Get-OriginShell
    $ticks = $shell.StartTime.ToUniversalTime().Ticks
    $root = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'CsvDashboardClient'
    if (-not $Create -and -not [IO.Directory]::Exists($root)) { return }
    if ($Create) {
        $directory = [IO.Directory]::CreateDirectory($root)
        $user = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = [Security.AccessControl.DirectorySecurity]::new()
        # Persist only the access rules. Audit rules require SeSecurityPrivilege.
        $acl.SetAccessRuleProtection($true, $false)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $user, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
        if ($PSVersionTable.PSEdition -eq 'Desktop') {
            $directory.SetAccessControl($acl)
        } else {
            [IO.FileSystemAclExtensions]::SetAccessControl($directory, $acl)
        }
    }

    foreach ($entry in Get-ChildItem -LiteralPath $root -File) {
        if ($entry.Name -match '^(\d+)-(\d+)-[0-9a-f]{64}\.(?:key|[0-9a-f]{32}\.tmp)$') {
            $recordPid = [int]$Matches[1]
            $recordTicks = [long]$Matches[2]
            $process = Get-Process -Id $recordPid -ErrorAction SilentlyContinue
            if ($process) {
                try { $liveTicks = $process.StartTime.ToUniversalTime().Ticks }
                catch { continue } # A process owned by another user may deny inspection.
                if ($liveTicks -eq $recordTicks) { continue }
            }
            Remove-Item -LiteralPath $entry.FullName -Force -ErrorAction SilentlyContinue
        }
    }

    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $serverHash = [BitConverter]::ToString($sha.ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($Base.AbsoluteUri))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }

    $stem = Join-Path $root "$($shell.Id)-$ticks-$serverHash"
    $keyFile = "$stem.key"
    if (-not [IO.File]::Exists($keyFile)) {
        if (-not $Create) { return }
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 32
        try { $random.GetBytes($bytes) } finally { $random.Dispose() }
        $secret = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
        $temp = "$stem.$([Guid]::NewGuid().ToString('N')).tmp"
        try {
            [IO.File]::WriteAllText($temp, $secret)
            try { [IO.File]::Move($temp, $keyFile) }
            catch [IO.IOException] { if (-not [IO.File]::Exists($keyFile)) { throw } }
        } finally { [IO.File]::Delete($temp) }
    }
    $secret = [IO.File]::ReadAllText($keyFile)
    if ($secret -cnotmatch '^[0-9a-f]{64}$') { throw 'The terminal ownership record is invalid.' }
    return $secret
}

$ErrorActionPreference = 'Stop'
$handler = $null
$client = $null
$stream = $null
$content = $null
$response = $null
try {
    $server = [Uri]$ServerUrl
    if (-not $server.IsAbsoluteUri -or $server.Scheme -notin @('http', 'https') -or
        $server.UserInfo -or $server.Query -or $server.Fragment) {
        throw 'Provide an HTTP or HTTPS dashboard URL without credentials, query, or fragment.'
    }
    Add-Type -AssemblyName System.Net.Http
    $base = [Uri]($server.AbsoluteUri.TrimEnd('/') + '/')
    if (-not $StopAll) {
        $file = Get-Item -LiteralPath $CsvFile
        if ($file -isnot [System.IO.FileInfo] -or $file.Extension -ine '.csv' -or $file.Length -eq 0) {
            throw 'Choose a nonempty local .csv file.'
        }
    }
    $credential = Get-ClientCredential $base (-not $StopAll)
    if (-not $credential) {
        Write-Host 'This terminal has no recorded launches for that server.'
        return
    }

    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $client = [System.Net.Http.HttpClient]::new($handler)
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $client.DefaultRequestHeaders.Add('X-Dashboard-Client-Owner', $credential)
    if ($StopAll) {
        $endpoint = [Uri]::new($base, 'api/client-stop-sessions')
        $content = [System.Net.Http.ByteArrayContent]::new([byte[]]@())
        $expectedStatus = 200
        $action = 'Stop'
    } else {
        $filename = [Uri]::EscapeDataString($file.Name)
        $cache = $Parquet.ToString().ToLowerInvariant()
        $endpoint = [Uri]::new($base, "api/client-load-csv?filename=$filename&parquet=$cache")
        $stream = $file.OpenRead()
        $content = [System.Net.Http.StreamContent]::new($stream)
        $content.Headers.ContentLength = $stream.Length
        $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new('text/csv')
        $expectedStatus = 201
        $action = 'Upload'
    }
    try {
        $response = $client.PostAsync($endpoint, $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    }
    catch {
        # PowerShell wraps .NET transport errors. Show the underlying cause.
        $detail = $_.Exception.GetBaseException().Message
        $authority = $base.GetLeftPart([UriPartial]::Authority)
        throw "$action request to $authority failed. $detail"
    }
    if ([int]$response.StatusCode -ne $expectedStatus) {
        $detail = $null
        try { $detail = ($body | ConvertFrom-Json).error } catch {}
        if (-not $detail -and [int]$response.StatusCode -in @(404, 405)) {
            $detail = "The server did not accept POST $($endpoint.AbsolutePath). Check the URL and restart the dashboard using run_server.py from the updated checkout."
        }
        if (-not $detail) { $detail = 'Check the dashboard URL and start the server with run_server.py.' }
        throw "$action failed (HTTP $([int]$response.StatusCode)). $detail"
    }

    $result = $body | ConvertFrom-Json
    if ($StopAll) {
        foreach ($field in @('stopped', 'cancelled', 'terminating')) {
            if ($null -eq $result.$field -or [string]$result.$field -notmatch '^\d+$') {
                throw 'The server returned an invalid stop response.'
            }
        }
        Write-Host "Stopped: $($result.stopped); uploads or links cancelled: $($result.cancelled); still terminating: $($result.terminating)."
        return
    }
    if ($result.launch_url -cnotmatch '^\./\?client_csv=[A-Za-z0-9_-]{43}$') {
        throw 'The server returned an invalid launch URL.'
    }
    $launch = [Uri]::new($base, [string]$result.launch_url)
    Start-Process -FilePath $launch.AbsoluteUri
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    foreach ($resource in @($response, $content, $stream, $client, $handler)) {
        if ($null -ne $resource) { $resource.Dispose() }
    }
}
