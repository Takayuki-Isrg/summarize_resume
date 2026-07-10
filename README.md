# レジュメ要約ツール
ShareXのスクロールキャプチャから作成したPDFをOCRし、個人情報をマスクしたうえでOpenAI APIに渡し、採用向けの経歴要約を生成するツールです。

## 主な機能
- PNGからPDF生成
- OCRによる文字抽出
- メールアドレス、電話番号、郵便番号、住所などの除去（全スクリプト共通）
- OpenAI APIによる経歴要約
- クリップボードコピー
- テキスト保存

## セットアップ

本READMEのコマンドは、Windowsの「PowerShell」で実行します。
スタートメニューから「PowerShell」と検索して起動してください。

### 1. 必要なソフトウェアのインストール

Python・ShareX・Tesseract OCR（日本語OCRエンジン）をまとめてインストールします。

```powershell
winget install --id Python.Python.3.11 -e
winget install --id ShareX.ShareX -e
winget install --id UB-Mannheim.TesseractOCR -e
```

※wingetによるインストールは、環境によっては管理者権限が必要になる場合があります
（エラーが出る場合は、PowerShellを管理者として実行してください）

```powershell
# インストールしたPythonのバージョン確認
python --version
```

### 2. 日本語OCRデータの配置

Tesseractの日本語モデルをダウンロードし、`tessdata`フォルダに配置します。

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/jpn.traineddata" -OutFile "$Env:ProgramFiles\Tesseract-OCR\tessdata\jpn.traineddata"
```

うまくいかない場合は、[配布元ページ](https://github.com/tesseract-ocr/tessdata/blob/main/jpn.traineddata)から手動でダウンロードし、`C:\Program Files\Tesseract-OCR\tessdata\` に置いてください。

### 3. OpenAI APIキーの発行と設定

本ツールでは OpenAI API を使用します。[こちら](https://platform.openai.com/login?next=%2Fapi-keys)でAPIキーを発行し、環境変数に設定してください。

```powershell
setx OPENAI_API_KEY "your_api_key_here"

# 設定した環境変数の確認 ※setx実行後は、新しいPowerShellを開いて実行してください
echo $Env:OPENAI_API_KEY
```

macOS / Linuxの場合:
```bash
export OPENAI_API_KEY="sk-..."
```

### 4. リポジトリの取得

Gitを利用できる場合は、以下で取得してください。

```powershell
git clone https://github.com/Takayuki-Isrg/summarize_resume.git
cd summarize_resume
```

Gitを使わない場合は、[ZIPファイル](https://github.com/Takayuki-Isrg/summarize_resume/archive/refs/heads/main.zip)をダウンロードして任意の場所に解凍し、`summarize_resume`フォルダに移動してください。

### 5. 仮想環境の作成と依存関係のインストール

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

以上でセットアップは完了です。

## 実行

ShareXでキャプチャした画像（またはOCR前のPDF）から、OCR・要約・クリップボードコピーまでを一括で行います。

```powershell
python ocr.py "画像またはPDFのパス" --copy
```

主なオプション:
- `--copy`: 要約結果をクリップボードにもコピー
- `--save <path>`: 要約結果の保存先を指定（未指定時はOCR後のPDFと同じ場所）
- `--model <name>`: 使用するモデル名（既定: gpt-4.1-mini）
- `--language <lang>`: ocrmypdfに渡すOCR言語（既定: jpn）
- `--keep-intermediate`: 中間生成物のPDFを残す

すでにOCR済みのPDFがあり、要約のみ行いたい場合は `summarize_resume.py` を直接使用できます。

```powershell
python summarize_resume.py "OCR済みPDFパス" --copy
```

## 想定フロー
1. ShareXでスクロールキャプチャ
2. `python ocr.py "キャプチャ画像のパス" --copy` を実行
   （内部でPDF化 → OCR → 個人情報マスク → 要約生成 → クリップボードコピーまで自動実行）

## 精度に関する注意
OCRおよび要約精度は、入力となるPDFの形式に依存します。
特に以下のケースでは精度が低下することがあります：

- ミイダスのレジュメPDF（レイアウトの影響）
- 画像品質が低いキャプチャ

要約結果は必ず人手で確認する前提としてください。

## 注意
- APIキーはリポジトリに含めない
- 実在候補者のPDFや要約結果はコミットしない

## 今後の改善予定

現在はレジュメ要約を主な対象としていますが、今後はミイダスのいいねユーザーに対して、
経歴要約とスカウトメッセージ案の作成を一連の流れで行えるようにすることを検討しています。

これにより、候補者確認からスカウト文面作成までの作業時間短縮を目指します。

なお、実際の時短効果や運用可否については、別途検証が必要です。

## 変更履歴

### 2026-07-10
- README: 実行手順を実態に合わせて修正（`ocr.py` による一括実行を主な手順として明記）。セットアップ手順を再構成して簡素化。
- `requirements.txt`: プロジェクトで実際に使用していない依存関係（nipype, nibabel, pyxnat, scipy, pandas など）を削除し、実際に使用するパッケージのみに整理。
- `summary_with_sources.py`: テキスト抽出後に個人情報マスク処理（`sanitize_text`）を適用するよう修正。
  修正前は、メールアドレス・電話番号・郵便番号・住所がマスクされないまま OpenAI API に送信されていた。
