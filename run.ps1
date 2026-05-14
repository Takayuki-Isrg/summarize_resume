param(
    [Parameter(Position = 0)]
    [string]$PdfPath,

    [string]$Model,

    [string]$Save,

    [switch]$Copy,

    [string]$Prompt
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

if ([string]::IsNullOrWhiteSpace($PdfPath)) {
    throw "PDFファイルのパスを指定してください。例: .\run.ps1 .\resume.pdf"
}

if (-not (Test-Path $PdfPath -PathType Leaf)) {
    throw "PDFファイルが見つかりません: $PdfPath"
}

if ([System.IO.Path]::GetExtension($PdfPath).ToLowerInvariant() -ne ".pdf") {
    throw "PDFファイルを指定してください: $PdfPath"
}

$activateScript = Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    throw "仮想環境が見つかりません。先に .\setup.ps1 を実行してください。"
}

. $activateScript

$entryPoint = Join-Path $projectRoot "main.py"
if (-not (Test-Path $entryPoint)) {
    $entryPoint = Join-Path $projectRoot "summarize_resume.py"
}

if (-not (Test-Path $entryPoint)) {
    throw "実行ファイルが見つかりません: main.py または summarize_resume.py"
}

$argsList = @($entryPoint, $PdfPath)

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $argsList += @("--model", $Model)
}

if (-not [string]::IsNullOrWhiteSpace($Save)) {
    $argsList += @("--save", $Save)
}

if ($Copy) {
    $argsList += "--copy"
}

if (-not [string]::IsNullOrWhiteSpace($Prompt)) {
    $argsList += @("--prompt", $Prompt)
}

python @argsList
