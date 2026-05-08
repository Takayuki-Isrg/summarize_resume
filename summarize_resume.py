import argparse
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import fitz  # PyMuPDF
import pyperclip
from openai import OpenAI, OpenAIError


Provider = Literal["openai", "ollama"]

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_MODEL = DEFAULT_OPENAI_MODEL
OLLAMA_BASE_URL = "http://localhost:11434/v1"
MAX_SOURCE_CHARS = 24000

DEFAULT_PROMPT = PROFILE_SYSTEM_PROMPT = """\
あなたは採用担当者向けに候補者レジュメを要約するアシスタントです。
入力される本文は OCR 済み PDF から抽出し、個人連絡先をマスク済みのテキストです。

以下の方針で、日本語で簡潔かつ実務的に要約してください。
- 採用判断に役立つ情報を優先する
- 氏名・メールアドレス・電話番号・郵便番号・住所などの個人連絡先には触れない
- OCR 由来のノイズがあっても文脈から補って解釈する
- 不明な点は断定せず、「記載なし」「判別しづらい」と表現する
- 候補者の経歴・スキルを誇張しない（盛らない）
- 記載されていない経験・スキルを推測で補完しない
- 技術スタックは、職務経歴書に明記されている内容のみを抽出する
- 「実務経験あり」と「知識レベル・学習のみ」は区別する（判別できる場合）
- 使用頻度や主軸技術が読み取れる場合は優先的に記載する
- 記載が不明確な技術は無理に補完せず、「記載あり（詳細不明）」とする

出力形式:
【候補者プロフィール要約】
- 技術スタック:
- 経験年数:
- 業務概要:
- 強み:
- 注意点:
"""

SCOUT_SYSTEM_PROMPT = """\
あなたはITエンジニア採用のスカウトメールを作成するアシスタントです。
候補者プロフィール要約をもとに、日本語で自然なビジネス文のスカウトメール下書きを作成してください。

条件:
- 丁寧で押しつけがましくない
- テンプレ感を減らし、候補者の経歴に具体的に触れる
- 長すぎない（件名 + 本文 500〜700字程度）
- 個人連絡先や住所には触れない
- 経歴にない内容を推測で追加しない

出力形式:
【スカウトメール下書き】
件名:
本文:
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


@dataclass(frozen=True)
class LLMConfig:
    provider: Provider
    model: str


class ChatLLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.client = self._build_client(config.provider)

    @staticmethod
    def _build_client(provider: Provider) -> OpenAI:
        if provider == "ollama":
            return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("環境変数 OPENAI_API_KEY が設定されていません。")
        return OpenAI(api_key=api_key)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
        except OpenAIError as exc:
            raise RuntimeError(
                f"LLM API呼び出しに失敗しました provider={self.config.provider} model={self.config.model}: {exc}"
            ) from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise RuntimeError("LLM APIから空の応答が返されました。")
        return content.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OCR済みPDFから文字を抽出し、候補者プロフィール要約とスカウトメール下書きを生成します。"
    )
    parser.add_argument("pdf_path", help="OCR済みPDFファイルのパス")
    parser.add_argument(
        "--provider",
        choices=["openai", "ollama"],
        default="openai",
        help="利用するLLMプロバイダー。既定値: openai",
    )
    parser.add_argument(
        "--model",
        help=f"使用するモデル名。未指定時: openai={DEFAULT_OPENAI_MODEL}, ollama={DEFAULT_OLLAMA_MODEL}",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="候補者プロフィール要約用のカスタムプロンプト。未指定時は内蔵プロンプトを使います。",
    )
    parser.add_argument(
        "--save",
        help="生成結果をテキスト保存するファイルパス",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="生成結果をクリップボードにもコピーします。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="ログレベル。既定値: INFO",
    )
    return parser


def resolve_model(provider: Provider, model: str | None) -> str:
    if model:
        return model
    if provider == "ollama":
        return DEFAULT_OLLAMA_MODEL
    return DEFAULT_OPENAI_MODEL


def validate_inputs(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"ファイルが見つかりません: {pdf_path}")
    if not pdf_path.is_file():
        raise SystemExit(f"ファイルではありません: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("PDFファイルを指定してください。")


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
                logging.warning("page=%s からテキストを抽出できませんでした。", page_number)
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


def trim_source_text(source_text: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    if len(source_text) <= max_chars:
        return source_text
    logging.warning(
        "入力テキストが長いため先頭 %s 文字に切り詰めます。元の文字数=%s",
        max_chars,
        len(source_text),
    )
    return source_text[:max_chars]


def generate_profile_summary(
    llm: ChatLLMClient, source_text: str, prompt: str = DEFAULT_PROMPT
) -> str:
    user_prompt = (
        "以下は OCR 済み PDF から抽出し、連絡先情報をマスクした候補者レジュメ本文です。\n"
        "採用判断に有用な情報だけを拾って指定形式で要約してください。\n\n"
        f"{source_text}"
    )
    return llm.complete(prompt, user_prompt)


def generate_scout_mail(llm: ChatLLMClient, profile_summary: str) -> str:
    user_prompt = (
        "以下の候補者プロフィール要約をもとに、スカウトメール下書きを作成してください。\n\n"
        f"{profile_summary}"
    )
    return llm.complete(SCOUT_SYSTEM_PROMPT, user_prompt)


def require_openai():
    return OpenAI


def summarize_text(client: OpenAI, model: str, prompt: str, source_text: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "以下は OCR 済み PDF から抽出し、連絡先情報をマスクした候補者レジュメ本文です。\n"
                    "採用判断に有用な情報だけを拾って要約してください。\n\n"
                    f"{source_text}"
                ),
            },
        ],
        temperature=0.3,
    )
    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise RuntimeError("LLM APIから空の応答が返されました。")
    return content.strip()


def build_output(profile_summary: str, scout_mail: str) -> str:
    return f"{profile_summary}\n\n---\n\n{scout_mail}"


def maybe_save(output_text: str, output_path: str | None) -> None:
    if not output_path:
        return
    Path(output_path).write_text(output_text, encoding="utf-8")
    logging.info("生成結果を保存しました: %s", output_path)


def maybe_copy(output_text: str, should_copy: bool) -> None:
    if not should_copy:
        return
    pyperclip.copy(output_text)
    logging.info("生成結果をクリップボードへコピーしました。")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="%(levelname)s:%(message)s")

    pdf_path = Path(args.pdf_path).expanduser().resolve()
    provider = cast(Provider, args.provider)
    model = resolve_model(provider, args.model)
    logging.info("provider=%s model=%s", provider, model)

    try:
        validate_inputs(pdf_path)
        extracted_text = extract_text_from_pdf(pdf_path)
        sanitized_text = sanitize_text(extracted_text)
        source_text = trim_source_text(sanitized_text)

        llm = ChatLLMClient(LLMConfig(provider=provider, model=model))
        profile_summary = generate_profile_summary(llm, source_text, args.prompt)
        scout_mail = generate_scout_mail(llm, profile_summary)
        output_text = build_output(profile_summary, scout_mail)

        maybe_save(output_text, args.save)
        maybe_copy(output_text, args.copy)
        print(output_text)
    except RuntimeError as exc:
        logging.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
