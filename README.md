# レジュメ要約ツール
ShareXのスクロールキャプチャから作成したPDFをOCRし、個人情報をマスクしたうえでOpenAI APIに渡し、採用向けの経歴要約を生成するツールです。

## 主な機能
- PNG/JPGなどの画像をPDF化せず直接OCR
- PDFはまずテキスト抽出し、十分に取れない場合のみOCR
- 入力形式（PNG / JPG / PDF）の自動判定
- OCRによる文字抽出
- メールアドレス、電話番号、郵便番号、住所などの除去
- OpenAI APIによる経歴要約
- OpenAI APIによるスカウトメール生成
- クリップボードコピー
- テキスト保存
- 各工程の処理時間ログ出力

## セットアップ

### 各種コマンドの実行環境について

- 本READMEのコマンドは、Windowsの「PowerShell」で実行します。
- スタートメニューから「PowerShell」と検索して起動してください。

※wingetによるインストールは、環境によっては管理者権限が必要になる場合があります  
（エラーが出る場合は、PowerShellを管理者として実行してください）

### OpenAI APIキーの発行およびWindows側環境変数の設定

本ツールでは OpenAI API を使用します。事前にAPIキーを発行し、環境変数に設定してください。
https://platform.openai.com/login?next=%2Fapi-keys

PowerShellで以下を実行してください：

```bash
# Windows
setx OPENAI_API_KEY "your_api_key_here"

# 設定した環境変数の確認 ※setx実行後の場合は、新しいPowerShellを開いて実行してください
echo $Env:OPENAI_API_KEY

# macOS / Linux
export OPENAI_API_KEY="sk-..."
```

### Pythonインストール
Python 3.10 以上を推奨します。

```bash
# Python 3.11のインストール
winget install --id Python.Python.3.11 -e

# インストールしたPythonのバージョン確認
python --version
```

### ShareXインストール
```bash
winget install --id ShareX.ShareX -e
```

### ZIPダウンロード
以下のリンクからZIPファイルをダウンロードしてください。

https://github.com/Takayuki-Isrg/summarize_resume/archive/refs/heads/main.zip

ダウンロード後、任意の場所に解凍してください。

### Git
Gitを利用できる場合は、以下でも取得可能です。
任意の作業ディレクトリで以下を実行してください。

```bash
git clone https://github.com/Takayuki-Isrg/summarize_resume.git
cd "summarize_resume"
```

### 仮想環境
ZIPを解凍（またはgit clone）すると、summarize_resume というフォルダが作成されます。
以下のコマンドを実行して、ダウンロードしたフォルダに移動します。

```bash
cd "summarize_resume"
```

その後、仮想環境を作成・有効化します。

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 依存関係
```bash
# requirements.txt内のパッケージ／ライブラリを全てインストールする
pip install -r requirements.txt
```

VS Codeで `pip install` 後も `import` 警告が残る場合は、VS Codeが古いPython環境情報を保持している可能性があります。
仮想環境が選択されていることを確認し、VS Codeを再起動してください。

## 実行
```bash
python summarize_resume.py "PDFパス" --copy
```

ShareX のキャプチャー結果から OCR、要約、スカウトメール生成まで一括実行する場合:

```bash
python ocr.py "画像またはPDFパス" --scout-mail --copy-mail --company-name "株式会社サンプル"
```

`ocr.py` は入力拡張子を自動判定します。PNG/JPGなどの画像はPDF化せず直接OCRし、PDFは先にテキスト抽出を試して、抽出文字数が少ない場合のみOCRします。
既定では200文字未満の場合にOCRへフォールバックします。必要に応じて `--min-text-chars 300` のように調整できます。

既存の要約テキストからスカウトメールだけを作る場合:

```bash
python scout_mail.py "要約テキストパス" --copy --company-name "株式会社サンプル"
```

OCR済みPDFを直接渡すこともできます。この場合は、PDFから候補者要約を生成してからスカウトメールを作成します。

```bash
python scout_mail.py "OCR済みPDFパス" --copy --company-name "株式会社サンプル"
```

スカウトメール生成は、現状の手動作成運用に合わせてミイダス向けを既定にしています。既定では、候補者アクションは `気になる`、募集ポジションは `特販部 / 営業`、希望勤務地は `名古屋 / 仙台 / 岡山`、文面で触れる勤務地は `名古屋` として扱います。

必要に応じて以下のように上書きできます。

```bash
python scout_mail.py "要約テキストパス" --copy --candidate-action "いいね" --desired-roles "営業" --desired-locations "仙台" --work-location "仙台"
```

### ShareX Actions 設定例
ShareX の `タスクの設定 > アクション` に外部アクションを追加し、After capture tasks で `Save image to file` と `Perform actions` を有効にします。

- File path: `C:\Python\summarize_resume\.venv\Scripts\python.exe`
- Arguments:

```text
"C:\Python\summarize_resume\ocr.py" "$input" --scout-mail --copy-mail --company-name "株式会社サンプル"
```

求人情報を長めに渡したい場合は、テキストファイルを用意して `--job-context-file "C:\path\job_context.txt"` を追加してください。

## 想定フロー
1. ShareXでスクロールキャプチャ
2. 入力形式を自動判定
3. 画像の場合は直接OCR
4. PDFの場合はまずテキスト抽出
5. PDFから十分なテキストが取れない場合のみOCR
6. 個人情報マスク
7. 要約生成
8. スカウトメール生成
9. クリップボードへコピー

## 処理時間ログ
処理時間は `sharex_resume.log` に出力されます。前処理が遅い場合は、まず `PDFテキスト抽出`、`画像OCR`、`PDF OCR`、`経歴要約生成`、`スカウトメール生成` の秒数を確認してください。

ログ出力例:

```text
2026-04-28 18:00:00 [INFO] 処理時間: 入力判定 0.00秒
2026-04-28 18:00:04 [INFO] 処理時間: 画像OCR 3.85秒
2026-04-28 18:00:04 [INFO] 処理時間: 前処理 3.86秒
2026-04-28 18:00:14 [INFO] 処理時間: 経歴要約生成 9.72秒
2026-04-28 18:00:24 [INFO] 処理時間: スカウトメール生成 10.11秒
2026-04-28 18:00:24 [INFO] 処理時間: 全体 24.20秒
```

## 精度に関する注意
OCRおよび要約精度は、入力となるPDFの形式に依存します。
特に以下のケースでは精度が低下することがあります：

- ミイダスのレジュメPDF（レイアウトの影響）
- 画像品質が低いキャプチャ

要約結果は必ず人手で確認する前提としてください。

## 注意
- APIキーはリポジトリに含めない
- 実在候補者のPDFや要約結果はコミットしない

## OCRについて
本ツールでは OCR に Tesseract OCR と ocrmypdf を使用します。画像入力は Tesseract OCR で直接テキスト化し、PDF入力でOCRが必要な場合は ocrmypdf を使用します。
事前に以下をインストールしてください。

- Tesseract OCR
- ocrmypdf
- jpn.traineddata

### TesseractOCR導入手順

```bash
# PowerShell（管理者権限）で実行：
winget install UB-Mannheim.TesseractOCR
```

その後、Pythonライブラリをインストールする
```bash
pip install ocrmypdf
```

### jpn.traineddata導入手順
公式配布元:
https://github.com/tesseract-ocr/tessdata/blob/main/jpn.traineddata

直接DL用:
https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/jpn.traineddata

次のフォルダに置く
C:\Program Files\Tesseract-OCR\tessdata\

## 今後の改善予定

現在はレジュメ要約とスカウトメッセージ案の作成を一連の流れで行えます。
今後は、求人票ごとのプロンプト切り替えや、スカウト文面のA/Bパターン生成などを検討します。

なお、実際の送信前には、候補者情報・求人内容・法務/コンプライアンス観点を人手で確認してください。

