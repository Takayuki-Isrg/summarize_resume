import argparse
import os
import re
from pathlib import Path
from typing import List, Dict

import fitz  # PyMuPDF
from openai import OpenAI

"""
概要:
OCR済みPDFからテキストを抽出し、
OpenAI APIを用いて出典付きの要約を生成するツール。

処理フロー:
1. PDF読み込み（PyMuPDF）
2. ページ単位でテキスト抽出
3. セクション推定（職務経歴・スキルなど）
4. OpenAI APIで要約生成（出典付き）
5. クリップボードコピーおよびファイル保存

使用方法:
python summary_with_sources.py <pdf_path> --copy

依存:
- openai
- pymupdf
- pyperclip（任意）
"""


DEFAULT_MODEL = "gpt-4.1-mini"

DEFAULT_PROMPT = """\
あなたは採用担当向けの要約アシスタントです。
入力される文章は、OCR済みの職務経歴書・レジュメ・履歴書のテキストです。
事実ベースで日本語要約を作成してください。

出力ルール:
- 次の5セクションを必ず使う
  1. 応募者概要
  2. 職歴
  3. 強み
  4. 懸念点
  5. 面接で確認すべき事項
- 各箇条書きの末尾に、必ず出典を付ける
- 出典形式は次のどちらか
  - [出典: Page X]
  - [出典: Page X / セクション名]
- 出典は、与えられた本文中のページ番号とセクション名だけを使うこと
- 出典を推測しないこと
- 情報不足なら、その旨を明記すること
- 誇張しないこと
- 箇条書き中心
- 600〜1000字程度を目安にすること
- 個人情報の読み取りが不確かな場合は「判読困難」や「OCR上不明」と明記すること
"""

SECTION_PATTERNS = [
    r"職務経歴",
    r"職歴",
    r"業務内容",
    r"担当業務",
    r"スキル",
    r"技術",
    r"資格",
    r"自己PR",
    r"学歴",
    r"志望動機",
    r"プロジェクト",
    r"経験",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR済みPDFから、出典付き要約を生成する"
    )
    parser.add_argument("pdf_path", help="OCR済みPDFのパス")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"使用モデル。既定: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--save",
        help="保存先。未指定なら PDF と同じ場所に .summary.txt を作る",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="要約をクリップボードにもコピーする",
    )
    parser.add_argument(
        "--dump-text",
        action="store_true",
        help="モデルへ渡す前の抽出テキストを .ocrtext.txt に保存する",
    )
    return parser


def validate_inputs(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"File not found: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"Not a file: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("Please provide a PDF file.")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Environment variable OPENAI_API_KEY is not set.")


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_sections(page_text: str) -> List[str]:
    found = []
    for pattern in SECTION_PATTERNS:
        if re.search(pattern, page_text, flags=re.IGNORECASE):
            found.append(pattern)
    # 重複除去しつつ順序維持
    deduped = []
    seen = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def extract_pdf_text_by_page(pdf_path: Path) -> List[Dict[str, str]]:
    doc = fitz.open(pdf_path)
    pages = []

    for idx, page in enumerate(doc, start=1):
        text = page.get_text("text")
        text = normalize_text(text)
        sections = detect_sections(text)
        section_str = " / ".join(sections) if sections else "不明"

        page_block = {
            "page": str(idx),
            "sections": section_str,
            "text": text,
        }
        pages.append(page_block)

    return pages


def build_model_input(pages: List[Dict[str, str]]) -> str:
    chunks = []
    for page in pages:
        header = f"[Page {page['page']}]\n[Sections: {page['sections']}]\n"
        body = page["text"] if page["text"] else "(OCRで本文抽出なし)"
        chunks.append(header + body)

    return "\n\n" + ("\n\n" + ("-" * 60) + "\n\n").join(chunks)


def summarize_text(client: OpenAI, model: str, prompt: str, source_text: str) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": prompt},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "以下はOCR済みPDFからページ単位で抽出した本文です。\n"
                            "各箇条書きの末尾に、必ず [出典: Page X] または "
                            "[出典: Page X / セクション名] を付けてください。\n\n"
                            f"{source_text}"
                        ),
                    }
                ],
            },
        ],
    )
    return response.output_text.strip()


def save_text(text: str, output_path: Path) -> None:
    output_path.write_text(text, encoding="utf-8")


def copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip
    except ImportError as exc:
        raise SystemExit("To use clipboard copy, run `pip install pyperclip`.") from exc
    pyperclip.copy(text)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path).expanduser().resolve()
    validate_inputs(pdf_path)

    pages = extract_pdf_text_by_page(pdf_path)
    source_text = build_model_input(pages)

    if args.dump_text:
        dump_path = pdf_path.with_suffix(".ocrtext.txt")
        save_text(source_text, dump_path)

    client = OpenAI()
    summary = summarize_text(
        client=client,
        model=args.model,
        prompt=DEFAULT_PROMPT,
        source_text=source_text,
    )

    output_path = Path(args.save) if args.save else pdf_path.with_suffix(".summary.txt")
    save_text(summary, output_path)

    if args.copy:
        copy_to_clipboard(summary)

    print(summary)
    print(f"\n[Saved] {output_path}")


if __name__ == "__main__":
    main()