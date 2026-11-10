$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $projectRoot '.runtime/sitl'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$source = 'https://firmware.ardupilot.org/Tools/MissionPlanner/sitl/CopterStable/'
$files = @('ArduCopter.elf', 'cygwin1.dll', 'cygstdc++-6.dll', 'cyggcc_s-seh-1.dll', 'cygiconv-2.dll', 'cygintl-8.dll', 'cyggcc_s-1.dll', 'cyggomp-1.dll', 'cygquadmath-0.dll', 'cygssp-0.dll', 'cygatomic-1.dll', 'git.txt')
foreach ($file in $files) {
    Write-Host "Downloading $file"
    Invoke-WebRequest -UseBasicParsing -Uri ($source + $file) -OutFile (Join-Path $destination $file) -TimeoutSec 90
}
Copy-Item -LiteralPath (Join-Path $destination 'ArduCopter.elf') -Destination (Join-Path $destination 'ArduCopter.exe')
$manifest = [ordered]@{ source = $source; downloadedAt = [DateTime]::UtcNow.ToString('o'); files = @() }
foreach ($file in $files) {
    $manifest.files += @{ name = $file; sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $destination $file)).Hash }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $destination 'manifest.json')
Write-Host 'Windows SITL downloaded. The default start-local.cmd uses Ubuntu WSL; see backend/README.md.'
