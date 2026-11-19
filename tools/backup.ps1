# Full TheLull project backup without engine-generated folders.
# Usage: powershell -File tools\backup.ps1 [-Dest H:\Backups] [-DriveDir <Google Drive folder>] [-Keep 5]
# Policy: AGENTS.md "Где живёт проект"; procedure: docs/setup/LOCAL_UE.md.
param(
    [string]$Dest = "H:\Backups",
    [string]$DriveDir = "",
    [int]$Keep = 5
)
$ErrorActionPreference = "Stop"

if (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue) {
    throw "Close Unreal Editor before backup: open packages may be saved half-way."
}

$Root = Split-Path -Parent $PSScriptRoot
$Exclude = @("Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs")
$Stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$Name = "TheLull_$Stamp.zip"
$Zip = Join-Path $Dest $Name

New-Item -ItemType Directory -Force $Dest | Out-Null
# Stage on the backup drive: C: has little free space.
$Stage = Join-Path $Dest "_stage_$Stamp"
robocopy $Root $Stage /E /XD $Exclude /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

# ZipFile keeps hidden items (.git) and has no 2 GB limit, unlike Compress-Archive.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($Stage, $Zip)
Remove-Item -Recurse -Force $Stage

# Verify the archive opens and is not empty.
$Archive = [IO.Compression.ZipFile]::OpenRead($Zip)
$Count = $Archive.Entries.Count
$Archive.Dispose()
if ($Count -eq 0) { throw "Empty archive: $Zip" }
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash

function Prune([string]$Dir) {
    Get-ChildItem $Dir -Filter "TheLull_*.zip" | Sort-Object Name -Descending |
        Select-Object -Skip $Keep | Remove-Item -Force
}
Prune $Dest

"{0}  {1:N1} MB  {2} files  SHA256 {3}" -f $Zip, ((Get-Item $Zip).Length / 1MB), $Count, $Hash

if ($DriveDir) {
    New-Item -ItemType Directory -Force $DriveDir | Out-Null
    $Copy = Join-Path $DriveDir $Name
    Copy-Item $Zip $Copy
    if ((Get-FileHash $Copy -Algorithm SHA256).Hash -ne $Hash) { throw "Drive copy hash mismatch: $Copy" }
    Prune $DriveDir
    "Copied to {0}, hash verified. Confirm cloud sync status in Explorer." -f $Copy
}
