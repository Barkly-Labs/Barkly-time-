$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'barkly_work_log.py'
if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Host "Could not find barkly_work_log.py in $PSScriptRoot" -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

# Find the Python interpreter that is available to this Windows account.
$pythonExe = $null
$pyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $candidate = (& $pyLauncher.Source -3 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
    if ($candidate -and (Test-Path -LiteralPath $candidate.Trim())) {
        $pythonExe = $candidate.Trim()
    }
}
if (-not $pythonExe) {
    $pythonCommand = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -and (Test-Path -LiteralPath $pythonCommand.Source)) {
        $pythonExe = $pythonCommand.Source
    }
}
if (-not $pythonExe) {
    Write-Host 'Python was not found. Install Python 3, then run this installer again.' -ForegroundColor Red
    Write-Host 'During Python setup, enable the Python launcher if offered.'
    Read-Host 'Press Enter to close'
    exit 1
}

$pythonw = Join-Path (Split-Path -Parent $pythonExe) 'pythonw.exe'
if (Test-Path -LiteralPath $pythonw) {
    $target = $pythonw
} else {
    $target = $pythonExe
    Write-Host 'pythonw.exe was not found; the logger may show a console window at login.' -ForegroundColor Yellow
}

$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Barkly Work Log.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.Arguments = '"' + $scriptPath + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Start the local Barkly Work Log when I sign in'
$shortcut.Save()

Write-Host ''
Write-Host 'Barkly Work Log will now start automatically when you sign in to Windows.' -ForegroundColor Green
Write-Host "Logger script: $scriptPath"
Write-Host "Startup shortcut: $shortcutPath"
Write-Host 'It runs quietly in the background. Open http://127.0.0.1:8765 to view the dashboard.'
Write-Host 'Keep this folder in its current location so the startup shortcut keeps working.'
Read-Host 'Press Enter to close'
