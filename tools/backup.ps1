# Full TheLull project backup without engine-generated folders.
# Usage: powershell -File tools\backup.ps1 [-Dest H:\Backups]
param([string]$Dest = "H:\Backups")
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Exclude = @("Binaries", "Intermediate", "Saved", "DerivedDataCache", ".vs")
$Stamp = Get-Date -Format "yyyy-MM-dd_HHmm"
$Zip = Join-Path $Dest "TheLull_$Stamp.zip"

New-Item -ItemType Directory -Force $Dest | Out-Null
# Stage on the backup drive: C: has little free space.
$Stage = Join-Path $Dest "_stage_$Stamp"
# robocopy keeps .git and skips generated folders at any depth.
robocopy $Root $Stage /E /XD $Exclude /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

# ZipFile keeps hidden items (.git) and has no 2 GB limit, unlike Compress-Archive.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($Stage, $Zip)
Remove-Item -Recurse -Force $Stage
"{0}  {1:N1} MB" -f $Zip, ((Get-Item $Zip).Length / 1MB)
