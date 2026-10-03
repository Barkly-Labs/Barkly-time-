$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'Barkly Work Log.lnk'
if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Host 'Removed Barkly Work Log from Windows startup.' -ForegroundColor Green
} else {
    Write-Host 'No Barkly Work Log startup shortcut was found.'
}
Write-Host 'Your Python script and SQLite database were not changed or deleted.'
Read-Host 'Press Enter to close'
