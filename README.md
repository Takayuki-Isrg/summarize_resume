# レジュメ要約ツール
ShareXのスクロールキャプチャから作成したPDFをOCRし、個人情報をマスクしたうえでOpenAI APIに渡し、採用向けの経歴要約を生成するツールです。

## 主な機能
- PNGからPDF生成
- OCRによる文字抽出
- メールアドレス、電話番号、郵便番号、住所などの除去
- OpenAI APIによる経歴要約
- クリップボードコピー
- テキスト保存

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

## 実行
```bash
python summarize_resume.py "PDFパス" --copy
```

## 想定フロー
1. ShareXでスクロールキャプチャ
2. PDF化
3. OCR
4. テキスト抽出
5. 個人情報マスク
6. 要約生成
7. クリップボードへコピー

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
本ツールでは OCR に ocrmypdf を使用します。
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

現在はレジュメ要約を主な対象としていますが、今後はミイダスのいいねユーザーに対して、
経歴要約とスカウトメッセージ案の作成を一連の流れで行えるようにすることを検討しています。

これにより、候補者確認からスカウト文面作成までの作業時間短縮を目指します。

別途なお、実際の時短効果や運用可否については、別途検証が必要です。

