from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from llm_provider import LLMClient, build_llm_client, get_provider, resolve_model
from summarize_resume import (
    DEFAULT_PROMPT as RESUME_SUMMARY_PROMPT,
    extract_text_from_pdf,
    maybe_copy,
    maybe_save,
    sanitize_text,
    summarize_text,
    validate_inputs,
)


DEFAULT_CANDIDATE_ACTION = "気になる"
DEFAULT_POSITION = "営業"
DEFAULT_DESIRED_ROLES = "営業"
DEFAULT_DESIRED_LOCATIONS = "東京"
DEFAULT_WORK_LOCATION = "東京"
DEFAULT_TONE = "感謝 → 共感 → 軽い提案。フラットで丁寧、押し売り感は出さない"
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp932")
MAX_RESUME_CONTEXT_CHARS = 12000

DEFAULT_PROMPT = """\
あなたはスカウト媒体運用に精通した採用担当者です。
入力される候補者情報は、OCR済みレジュメから抽出し、個人連絡先をマスク済みの情報です。

以下の条件を満たす「スカウト媒体で“気になる”などのリアクションをしてくれたユーザー向けスカウトメール文面」を作成してください。

【前提】
- 媒体: スカウト媒体
- 対象: 「気になる」または入力された候補者アクションをしてくれたユーザー
- 手動作成の対象媒体は現状スカウト媒体のみ
- PG/SE希望ユーザーからの「いいね」は少ないため、営業職向けを標準にする
- 目的:
  - 「興味を持ってくれてありがとう」という姿勢を伝える
  - 警戒心を下げ、「一度話を聞いてみようかな」と思ってもらう
- トーン:
  - 感謝 → 共感 → 軽い提案、の流れ
  - フラットで丁寧、押し売り感は出さない
- 文字数:
  - 通常スカウトよりやや短め
  - スマホで読んでも負担にならない分量

【必ず盛り込む内容】
1. 冒頭で候補者アクションをしてくれたことへのお礼
2. なぜ連絡したのか（希望職種・志向とポジションの接点）
3. 営業職の簡単な特徴・魅力
   - お客様との関係性
   - 提案の幅や裁量
4. 勤務地で働くイメージが湧く一言
5. 応募ではなく、まずは情報交換・カジュアル面談でもOKという安心感
6. 相手の意思を尊重する締め方（返信の自由度を明示）

【表現上の注意】
- 「スカウト感」より「リアクションへのお返事」に近い温度感
- 上から目線・選考感は出さない
- スカウト媒体でよくある定型文っぽさを避ける
- 候補者アクション欄が「いいね」の場合は、件名・本文も「いいね」に合わせる
- 氏名・メールアドレス・電話番号・住所などの個人連絡先には触れない
- レジュメに書かれていない経験・スキル・志向性を推測で補完しない
- 会社名・職種・募集背景・待遇など、入力されていない情報を断定しない
- 過度な賛辞、煽り、押し付ける表現は避ける
- 日程調整や面談提案の文脈でも「面接」という文言は使わない

出力形式:
件名: ...

本文:
...
"""


@dataclass(frozen=True)
class ScoutMailRequest:
    candidate_summary: str
    sanitized_resume_text: str = ""
    company_name: str = ""
    position: str = DEFAULT_POSITION
    sender_name: str = ""
    job_context: str = ""
    candidate_action: str = DEFAULT_CANDIDATE_ACTION
    desired_roles: str = DEFAULT_DESIRED_ROLES
    desired_locations: str = DEFAULT_DESIRED_LOCATIONS
    work_location: str = DEFAULT_WORK_LOCATION
    tone: str = DEFAULT_TONE


def _value_or_not_set(value: str) -> str:
    cleaned = value.strip()
    return cleaned if cleaned else "未指定"


def _truncate_text(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n\n[以降は文字数上限のため省略]"


def build_user_prompt(request: ScoutMailRequest) -> str:
    resume_context = _truncate_text(
        request.sanitized_resume_text,
        MAX_RESUME_CONTEXT_CHARS,
    )

    return f"""\
以下の情報をもとに、スカウトメールを作成してください。

【会社名】
{_value_or_not_set(request.company_name)}

【募集ポジション】
{_value_or_not_set(request.position)}

【候補者アクション】
{_value_or_not_set(request.candidate_action)}

【候補者の希望職種】
{_value_or_not_set(request.desired_roles)}

【候補者の希望勤務地】
{_value_or_not_set(request.desired_locations)}

【文面で触れる勤務地】
{_value_or_not_set(request.work_location)}

【送信者名】
{_value_or_not_set(request.sender_name)}

【文面トーン】
{_value_or_not_set(request.tone)}

【求人・会社側の補足情報】
{_value_or_not_set(request.job_context)}

【候補者サマリー】
{request.candidate_summary.strip()}

【候補者レジュメ本文（連絡先マスク済み。根拠確認用）】
{resume_context if resume_context else "未指定"}
"""


def generate_scout_mail(
    llm_client: LLMClient,
    model: str,
    request: ScoutMailRequest,
    prompt: str = DEFAULT_PROMPT,
) -> str:
    return llm_client.complete(model, prompt, build_user_prompt(request))


def read_text_file(path: str | None) -> str:
    if not path:
        return ""
    return read_text_path(Path(path).expanduser().resolve())


def read_text_path(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        raise SystemExit(
            "PDFはテキストファイルとして読み込めません。"
            f"要約テキストではなくPDFを指定した可能性があります: {path}"
        )

    data = path.read_bytes()
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    encodings = ", ".join(TEXT_ENCODINGS)
    raise SystemExit(
        f"テキストファイルの文字コードを判定できませんでした: {path}\n"
        f"対応している文字コード: {encodings}"
    )


def build_summary_from_pdf(llm_client: LLMClient, model: str, pdf_path: Path) -> tuple[str, str]:
    validate_inputs(pdf_path)
    extracted_text = extract_text_from_pdf(pdf_path)
    sanitized_text = sanitize_text(extracted_text)
    summary_text = summarize_text(
        llm_client,
        model,
        RESUME_SUMMARY_PROMPT,
        sanitized_text,
    )
    return summary_text, sanitized_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="候補者要約テキストまたはOCR済みPDFからスカウトメールを生成します。"
    )
    parser.add_argument(
        "source_path",
        help="候補者要約テキスト、またはOCR済みPDFのパス",
    )
    parser.add_argument(
        "--resume-text-path",
        help="根拠確認用のレジュメ本文テキスト。未指定でも生成できます。",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="使用するモデル名。未指定時は選択中のプロバイダーの <PROVIDER>_MODEL 環境変数を使用します。",
    )
    parser.add_argument(
        "--company-name",
        default=os.getenv("SCOUT_COMPANY_NAME", ""),
        help="メール本文に入れる会社名。環境変数 SCOUT_COMPANY_NAME でも指定できます。",
    )
    parser.add_argument(
        "--position",
        default=os.getenv("SCOUT_POSITION", DEFAULT_POSITION),
        help="募集ポジション名。環境変数 SCOUT_POSITION でも指定できます。",
    )
    parser.add_argument(
        "--candidate-action",
        default=os.getenv("SCOUT_CANDIDATE_ACTION", DEFAULT_CANDIDATE_ACTION),
        help="候補者の媒体上アクション。既定値: 気になる",
    )
    parser.add_argument(
        "--desired-roles",
        default=os.getenv("SCOUT_DESIRED_ROLES", DEFAULT_DESIRED_ROLES),
        help="候補者の希望職種。既定値: 営業職",
    )
    parser.add_argument(
        "--desired-locations",
        default=os.getenv("SCOUT_DESIRED_LOCATIONS", DEFAULT_DESIRED_LOCATIONS),
        help="候補者の希望勤務地。既定値: 東京",
    )
    parser.add_argument(
        "--work-location",
        default=os.getenv("SCOUT_WORK_LOCATION", DEFAULT_WORK_LOCATION),
        help="文面で触れる勤務地。既定値: 東京",
    )
    parser.add_argument(
        "--sender-name",
        default=os.getenv("SCOUT_SENDER_NAME", ""),
        help="送信者名。環境変数 SCOUT_SENDER_NAME でも指定できます。",
    )
    parser.add_argument(
        "--job-context",
        default=os.getenv("SCOUT_JOB_CONTEXT", ""),
        help="求人・会社側の補足情報。環境変数 SCOUT_JOB_CONTEXT でも指定できます。",
    )
    parser.add_argument(
        "--job-context-file",
        default=os.getenv("SCOUT_JOB_CONTEXT_FILE", ""),
        help="求人・会社側の補足情報を記載したテキストファイル。",
    )
    parser.add_argument(
        "--tone",
        default=os.getenv("SCOUT_TONE", DEFAULT_TONE),
        help="文面トーン。環境変数 SCOUT_TONE でも指定できます。",
    )
    parser.add_argument(
        "--save",
        help="スカウトメールの保存先。未指定時は要約と同じ場所に .scout-mail.txt を作ります。",
    )
    parser.add_argument(
        "--summary-save",
        help="PDFから生成した候補者要約の保存先。PDF入力時のみ使います。",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="生成したスカウトメールをクリップボードにもコピーします。",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    provider = get_provider()
    model = resolve_model(provider, args.model)
    llm_client = build_llm_client(provider)

    source_path = Path(args.source_path).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"入力ファイルが見つかりません: {source_path}")

    job_context = args.job_context
    file_context = read_text_file(args.job_context_file)
    if file_context:
        job_context = f"{job_context}\n\n{file_context}".strip()

    if source_path.suffix.lower() == ".pdf":
        candidate_summary, sanitized_resume_text = build_summary_from_pdf(
            llm_client,
            model,
            source_path,
        )
        summary_output_path = (
            Path(args.summary_save)
            if args.summary_save
            else source_path.with_suffix(".summary.txt")
        )
        maybe_save(candidate_summary, str(summary_output_path))
    else:
        candidate_summary = read_text_path(source_path)
        sanitized_resume_text = read_text_file(args.resume_text_path)

    request = ScoutMailRequest(
        candidate_summary=candidate_summary,
        sanitized_resume_text=sanitized_resume_text,
        company_name=args.company_name,
        position=args.position,
        sender_name=args.sender_name,
        job_context=job_context,
        candidate_action=args.candidate_action,
        desired_roles=args.desired_roles,
        desired_locations=args.desired_locations,
        work_location=args.work_location,
        tone=args.tone,
    )

    scout_mail = generate_scout_mail(llm_client, model, request)

    output_path = (
        Path(args.save) if args.save else source_path.with_suffix(".scout-mail.txt")
    )
    maybe_save(scout_mail, str(output_path))
    maybe_copy(scout_mail, args.copy)

    print(scout_mail)
    print(f"\nスカウトメール保存先: {output_path}")


if __name__ == "__main__":
    main()
