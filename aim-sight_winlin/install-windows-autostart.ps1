param(
    [string]$ScriptDirectory = $PSScriptRoot
)

$launcher = Join-Path $ScriptDirectory "aim-sight-crossplat.pyw"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Could not find $launcher"
}

$python = Get-Command pyw.exe -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command pythonw.exe -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Could not find pyw.exe or pythonw.exe. Install Python for Windows first."
}

$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Aim Sight.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python.Source
$shortcut.Arguments = "`"$launcher`" tray"
$shortcut.WorkingDirectory = $ScriptDirectory
$shortcut.Description = "Start Aim Sight"
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,43"
$shortcut.Save()

Write-Host "Aim Sight startup shortcut created: $shortcutPath"
