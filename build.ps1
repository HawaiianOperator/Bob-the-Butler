$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
pnpm install --frozen-lockfile
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
cargo test --manifest-path src-tauri/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw 'Protocol checks failed.' }
python -m unittest discover -s uno-q -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) { throw 'UNO Q receiver checks failed.' }
pnpm tauri build
if ($LASTEXITCODE -ne 0) { throw 'Tauri build failed.' }
Copy-Item -LiteralPath '.\src-tauri\target\release\bob-the-butler.exe' -Destination '.\DeviceCompanion.exe' -Force
Write-Host 'Ready: DeviceCompanion.exe; installer in src-tauri/target/release/bundle/nsis/'
