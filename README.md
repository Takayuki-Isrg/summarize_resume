# Resume Summary Tool

OCR済みの職務経歴書PDFからテキストを抽出し、個人情報をマスクしたうえで、採用担当向けの候補者プロフィール要約とスカウトメール下書きを生成するCLIツールです。
OpenAI API と Ollama（OpenAI互換API）を切り替えて利用できます。

## 主な機能
- OCR済みPDFからのテキスト抽出
- メールアドレス、電話番号、郵便番号、住所などのマスク
- 候補者プロフィール要約の生成
- スカウトメール下書きの生成
- OpenAI API / Ollama の切替
- クリップボードコピー
- テキスト保存

## セットアップ

### Pythonインストール
Python 3.12 を想定しています。

```bash
winget install --id Python.Python.3.12 -e
python --version
```

### ShareXインストール
```bash
winget install --id ShareX.ShareX -e
```

### 仮想環境
```bash
python -m venv .venv
.venv\Scripts\activate
```

### 依存関係
```bash
pip install -r requirements.txt
```

## OpenAIで利用する場合

### APIキー作成・設定
1. OpenAI PlatformでAPIキーを作成
   - https://platform.openai.com/api-keys
2. 環境変数 `OPENAI_API_KEY` に設定

```bash
# Windows PowerShell
setx OPENAI_API_KEY "sk-..."

# 新しいPowerShellを開いて確認
echo $env:OPENAI_API_KEY
```

### 実行例
```bash
python summarize_resume.py "PDFパス" --provider openai --model gpt-4.1-mini --save result.txt
```

## Ollamaでローカル利用する場合

### Ollamaインストール
```bash
winget install --id Ollama.Ollama -e
ollama --version
```

### モデル取得
```bash
ollama pull qwen3:8b
ollama pull gpt-oss:20b
```

Ollamaは `http://localhost:11434/v1` をOpenAI互換APIとして利用します。

### 実行例
```bash
python summarize_resume.py "PDFパス" --provider ollama --model qwen3:8b --save result.txt
python summarize_resume.py "PDFパス" --provider ollama --model gpt-oss:20b --copy
```

## CLI usage

```bash
# 既定値: --provider openai --model gpt-4.1-mini
python summarize_resume.py "PDFパス"

# OpenAIのモデルを指定
python summarize_resume.py "PDFパス" --provider openai --model gpt-4.1-mini

# Ollamaのモデルを指定
python summarize_resume.py "PDFパス" --provider ollama --model qwen3:8b

# 結果を保存し、ログを詳しく出す
python summarize_resume.py "PDFパス" --provider ollama --model qwen3:8b --save result.txt --log-level DEBUG
```

## 出力内容
1. 候補者プロフィール要約
   - 技術スタック
   - 経験年数
   - 業務概要
   - 強み
   - 注意点
2. スカウトメール下書き
   - 件名
   - 本文

## 想定フロー
1. ShareXでスクロールキャプチャ
2. PDF化 / OCR
3. テキスト抽出
4. 個人情報マスク
5. 候補者プロフィール要約生成
6. スカウトメール下書き生成
7. クリップボードコピーまたはテキスト保存

## 注意
- APIキーはリポジトリに含めない
- 実在候補者のPDFや生成結果はコミットしない
- Ollama利用時は事前にOllamaアプリを起動しておく
- OCRノイズが多いPDFでは、出力の「注意点」を確認する

## OCRについて
本ツールでは OCR 済み PDF を入力として想定しています。
未OCRの画像・PDFから作成する場合は ocrmypdf を使用します。

- Tesseract OCR
- ocrmypdf
- jpn.traineddata

### TesseractOCR導入手順
```bash
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
