# Resume Summary Tool

ShareXのスクロールキャプチャから作成したPDFをOCRし、個人情報をマスクしたうえでOpenAI APIに渡し、採用向けの経歴要約を生成するツールです。

## 主な機能
- PNGからPDF生成
- OCRによる文字抽出
- メールアドレス、電話番号、郵便番号などのマスク
- OpenAI APIによる経歴要約
- クリップボードコピー
- テキスト保存

## セットアップ（Windows PowerShell前提）

このREADMEのコマンド例は Windows 11 の PowerShell を前提にしています。

### 初回セットアップ
Python 3.12 を想定しています。未インストールの場合は先に導入してください。

```powershell
winget install --id Python.Python.3.12 -e
python --version
```

依存関係のインストールと仮想環境作成は `setup.ps1` でまとめて実行できます。

```powershell
.\setup.ps1
```

`setup.ps1` は次を行います。
- Python の存在確認
- `.venv` の作成
- `requirements.txt` のインストール
- `.env.example` がある場合の案内

### ShareXインストール
```powershell
winget install --id ShareX.ShareX -e
```

### OpenAI APIキー設定
OpenAI APIを使うため、環境変数 `OPENAI_API_KEY` を設定してください。

```powershell
setx OPENAI_API_KEY "sk-..."

# 新しいPowerShellを開いて確認
echo $env:OPENAI_API_KEY
```

## 実行方法

通常は `run.ps1` を使います。`run.ps1` は `.venv` を有効化し、PDF引数を確認してからCLIを実行します。

```powershell
.\run.ps1 "PDFパス"
```

モデル指定、保存、クリップボードコピーも指定できます。

```powershell
.\run.ps1 "PDFパス" -Model gpt-4.1-mini
.\run.ps1 "PDFパス" -Save result.txt
.\run.ps1 "PDFパス" -Copy
```

`main.py` がある構成では `run.ps1` が `main.py` を実行します。このリポジトリの現在の構成では、互換のため `summarize_resume.py` を実行します。

## 想定フロー
1. ShareXでスクロールキャプチャ
2. PDF化
3. OCR
4. テキスト抽出
5. 個人情報マスク
6. 要約生成
7. クリップボードへコピー

## 注意
- APIキーはリポジトリに含めない
- 実在候補者のPDFや要約結果はコミットしない
- PowerShellで `.ps1` の実行がブロックされる場合は、実行ポリシーを確認する

## OCRについて
本ツールでは OCR に ocrmypdf を使用します。
事前に以下をインストールしてください。

- Tesseract OCR
- ocrmypdf
- jpn.traineddata

### TesseractOCR導入手順
```powershell
winget install UB-Mannheim.TesseractOCR
pip install ocrmypdf
```

### jpn.traineddata導入手順
公式配布元:
https://github.com/tesseract-ocr/tessdata/blob/main/jpn.traineddata

直接DL用:
https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/jpn.traineddata

次のフォルダに置く:
```text
C:\Program Files\Tesseract-OCR\tessdata\
```
