# Resume Summary Tool

ShareXのスクロールキャプチャから作成したPDFをOCRし、個人情報をマスクしたうえでOpenAI APIに渡し、採用向けの経歴要約を生成するツールです。

## 主な機能
- PNGからPDF生成
- OCRによる文字抽出
- メールアドレス、電話番号、郵便番号などのマスク
- OpenAI APIによる経歴要約
- クリップボードコピー
- テキスト保存

## セットアップ
```bash
winget install --id ShareX.ShareX -e
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 実行
```bash
python summarize_resume.py "PDFパス"
```

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

## OCRについて
本ツールでは OCR に ocrmypdf を使用します。
事前に以下をインストールしてください。

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

次のフォルダに置く
C:\Program Files\Tesseract-OCR\tessdata\

