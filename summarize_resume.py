import argparse
import os
import re
from pathlib import Path

import fitz  # PyMuPDF


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_PROMPT = """\
あなたは採用担当者向けに候補者レジュメを要約するアシスタントです。
入力される本文は OCR 済み PDF から抽出し、個人連絡先をマスク済みのテキストです。

以下の方針で、日本語で簡潔かつ実務的に要約してください。
- 採用判断に役立つ情報を優先する
- 氏名・メールアドレス・電話番号・郵便番号・住所などの個人連絡先には触れない
- OCR 由来のノイズがあっても文脈から補って解釈する
- 不明な点は断定せず、「記載なし」「判別しづらい」と表現する

出力形式:
【候補者サマリー】
- 概要:
- 経験年数:
- 直近の役割:
- 強み:

【経験・スキル】
- 主な業務経験:
- 技術・ツール:
- 業界/ドメイン:
- マネジメント経験:

【補足】
- 気になる点:
- 面談で確認したい点:
"""

EMAIL_PATTERN = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b"
)
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+81[-\s]?)?(?:0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4})(?!\d)"
)
POSTAL_PATTERN = re.compile(r"〒?\s*\d{3}-?\d{4}")
ADDRESS_PATTERN = re.compile(
    r"(?:(?:東京都|北海道|(?:京都|大阪)府|.{2,3}県))"
    r".{0,40}?"
    r"(?:市|区|町|村).{0,40}?(?:\d{1,4}-\d{1,4}(?:-\d{1,4})?)?"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR済みPDFから文字を抽出し、個人情報をマスクしたうえで OpenAI API による候補者要約を行います。"
    )
    parser.add_argument("pdf_path", help="OCR済みPDFファイルのパス")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"使用するモデル名。既定値: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="要約用のカスタムプロンプト。未指定時は内蔵プロンプトを使います。",
    )
    parser.add_argument(
        "--save",
        help="要約結果をテキスト保存するファイルパス",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="要約結果をクリップボードにもコピーします。pyperclip が必要です。",
    )
    return parser


def require_openai():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "openai パッケージがインストールされていません。`pip install openai` を実行してください。"
        ) from exc
    return OpenAI


def validate_inputs(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"ファイルが見つかりません: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"ファイルではありません: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("PDFファイルを指定してください。")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("環境変数 OPENAI_API_KEY が設定されていません。")


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(pdf_path: Path) -> str:
    chunks: list[str] = []

    with fitz.open(pdf_path) as doc:
        for page_number, page in enumerate(doc, start=1):
            page_text = normalize_text(page.get_text("text"))
            if not page_text:
                continue
            chunks.append(f"[Page {page_number}]\n{page_text}")

    if not chunks:
        raise SystemExit(
            "PDFからテキストを抽出できませんでした。OCR済みPDFかどうか確認してください。"
        )

    return "\n\n".join(chunks)


def sanitize_text(text: str) -> str:
    sanitized = text
    sanitized = EMAIL_PATTERN.sub("[メールアドレス削除済み]", sanitized)
    sanitized = PHONE_PATTERN.sub("[電話番号削除済み]", sanitized)
    sanitized = POSTAL_PATTERN.sub("[郵便番号削除済み]", sanitized)
    sanitized = ADDRESS_PATTERN.sub("[住所削除済み]", sanitized)
    return sanitized


def summarize_text(client, model: str, prompt: str, source_text: str) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": prompt}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "以下は OCR 済み PDF から抽出し、連絡先情報をマスクした候補者レジュメ本文です。\n"
                            "採用判断に有用な情報だけを拾って要約してください。\n\n"
                            f"{source_text}"
                        ),
                    }
                ],
            },
        ],
    )
    return response.output_text.strip()


def maybe_save(summary_text: str, output_path: str | None) -> None:
    if not output_path:
        return
    Path(output_path).write_text(summary_text, encoding="utf-8")


def maybe_copy(summary_text: str, should_copy: bool) -> None:
    if not should_copy:
        return
    try:
        import pyperclip
    except ImportError as exc:
        raise SystemExit(
            "--copy を使うには pyperclip が必要です。`pip install pyperclip` を実行してください。"
        ) from exc
    pyperclip.copy(summary_text)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).expanduser().resolve()
    validate_inputs(pdf_path)

    extracted_text = extract_text_from_pdf(pdf_path)
    sanitized_text = sanitize_text(extracted_text)

    OpenAI = require_openai()
    client = OpenAI()
    summary_text = summarize_text(client, args.model, args.prompt, sanitized_text)

    maybe_save(summary_text, args.save)
    maybe_copy(summary_text, args.copy)
    print(summary_text)


if __name__ == "__main__":
    main()
