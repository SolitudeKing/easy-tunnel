[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [string]$FilePath,
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

function Find-InnoSetupCompiler {
    $command = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $programFilesRoots = @(
        ${env:ProgramFiles(x86)},
        $env:ProgramFiles
    ) | Where-Object { $_ }

    foreach ($programFilesRoot in $programFilesRoots) {
        $compiler = Get-ChildItem `
            -Path (Join-Path $programFilesRoot "Inno Setup *\ISCC.exe") `
            -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName

        if ($compiler) {
            return $compiler
        }
    }

    throw "Inno Setup compiler was not found. Install Inno Setup 6, or run: choco install innosetup --yes"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot

try {
    $version = (& python -c "from easytunnel import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        throw "Unable to read easytunnel.__version__."
    }

    if (-not $OutputDir) {
        $OutputDir = Join-Path "release\manual" $version
    }

    if ([IO.Path]::IsPathRooted($OutputDir)) {
        $outputPath = $OutputDir
    }
    else {
        $outputPath = Join-Path $repoRoot $OutputDir
    }

    $outputPath = [IO.Path]::GetFullPath($outputPath)
    if (Test-Path -LiteralPath $outputPath) {
        throw "Output directory already exists: $outputPath. Use a new -OutputDir or remove it manually."
    }

    $pythonOutputDir = Join-Path $outputPath "python"
    $windowsOutputDir = Join-Path $outputPath "windows"
    $installerOutputDir = Join-Path $outputPath "installer"
    New-Item -ItemType Directory -Force -Path $pythonOutputDir, $windowsOutputDir, $installerOutputDir | Out-Null

    if (-not $SkipTests) {
        Invoke-CheckedCommand -Name "Tests" -FilePath "python" -Arguments @("-m", "pytest", "-q")
    }

    Invoke-CheckedCommand `
        -Name "Python distribution build" `
        -FilePath "python" `
        -Arguments @("-m", "build", "--outdir", $pythonOutputDir)

    $env:FLET_CLI_NO_RICH_OUTPUT = "1"
    $env:PYTHONUTF8 = "1"
    $fletArguments = @(
        "build",
        "windows",
        "--output", $windowsOutputDir,
        "--build-version", $version,
        "--project", "EasyTunnel",
        "--product", "EasyTunnel",
        "--company", "SolitudeKing",
        "--copyright", "Copyright (c) 2026 SolitudeKing",
        "--exclude", ".git", ".github", ".pytest_cache", ".venv", "build", "dist", "docs", "installer", "release", "storage", "tests"
    )
    Invoke-CheckedCommand -Name "Windows application build" -FilePath "flet" -Arguments $fletArguments

    $applicationPath = Join-Path $windowsOutputDir "EasyTunnel.exe"
    if (-not (Test-Path -LiteralPath $applicationPath -PathType Leaf)) {
        throw "EasyTunnel.exe was not found in the build output: $applicationPath"
    }

    $env:EASYTUNNEL_VERSION = $version
    $env:EASYTUNNEL_SOURCE_DIR = $windowsOutputDir
    $env:EASYTUNNEL_OUTPUT_DIR = $installerOutputDir
    $innoSetupCompiler = Find-InnoSetupCompiler
    Invoke-CheckedCommand `
        -Name "Windows installer build" `
        -FilePath $innoSetupCompiler `
        -Arguments @("installer/EasyTunnel.iss")

    $installerPath = Join-Path $installerOutputDir "EasyTunnel-Setup-$version.exe"
    if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
        throw "Installer was not found: $installerPath"
    }

    $checksumPath = "$installerPath.sha256"
    $checksum = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content `
        -LiteralPath $checksumPath `
        -Value "$checksum *$(Split-Path -Path $installerPath -Leaf)" `
        -Encoding ascii

    Write-Host "Packaging completed:"
    Write-Host "  Python distributions: $pythonOutputDir"
    Write-Host "  Windows application: $windowsOutputDir"
    Write-Host "  Installer: $installerPath"
    Write-Host "  SHA-256: $checksumPath"
}
finally {
    Pop-Location
}
