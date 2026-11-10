$ErrorActionPreference = 'Stop'
$playbackRoot = $PSScriptRoot
$playbackPython = Join-Path $playbackRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $playbackPython)) {
    & python -m venv (Join-Path $playbackRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a Python virtual environment.' }
}
& $playbackPython -m pip install -e $playbackRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not install dependencies.' }
$playbackShell = New-Object -ComObject WScript.Shell
$playbackShortcut = $playbackShell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Phone Playback.lnk'))
$playbackShortcut.TargetPath = Join-Path $playbackRoot '.venv\Scripts\pythonw.exe'
$playbackShortcut.Arguments = '-m phone_playback'
$playbackShortcut.WorkingDirectory = $playbackRoot
$playbackShortcut.IconLocation = ((Join-Path $playbackRoot 'docs\phone-playback.ico') + ',0')
$playbackShortcut.Description = 'Control phone audio through KDE Connect'
$playbackShortcut.Save()
Write-Output 'Installed. Open Phone Playback from the desktop. Pair the phone in KDE Connect first.'
