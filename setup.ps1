$ErrorActionPreference = "Stop"

function Get-PythonCommand {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & py -3.11.9 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "py"; Arguments = @("-3.11.9") }
        }

        & py -3 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "py"; Arguments = @("-3") }
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{ Command = "python"; Arguments = @() }
        }
    }

    throw "Python が見つかりません。README の手順に従って Python 3.11.9 をインストールしてください。"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Get-PythonCommand
Write-Host "Python を確認しました:"
& $python.Command @($python.Arguments + @("--version"))

$venvPath = Join-Path $projectRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "仮想環境を作成します: .venv"
    & $python.Command @($python.Arguments + @("-m", "venv", ".venv"))
}
else {
    Write-Host "仮想環境は作成済みです: .venv"
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "仮想環境の Python が見つかりません: $venvPython"
}

Write-Host "pip を更新します。"
& $venvPython -m pip install --upgrade pip

$requirements = Join-Path $projectRoot "requirements.txt"
if (Test-Path $requirements) {
    Write-Host "requirements.txt をインストールします。"
    & $venvPython -m pip install -r $requirements
}
else {
    Write-Host "requirements.txt が見つからないため、依存関係のインストールをスキップします。"
}

$envExample = Join-Path $projectRoot ".env.example"
if (Test-Path $envExample) {
    Write-Host ".env.example があります。必要に応じて .env にコピーし、値を設定してください。"
    Write-Host "例: Copy-Item .env.example .env"
}
else {
    Write-Host ".env.example はありません。OpenAI を使う場合は OPENAI_API_KEY を環境変数に設定してください。"
}

Write-Host "セットアップ完了。実行例: .\run.ps1 .\sample.pdf"
