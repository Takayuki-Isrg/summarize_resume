import argparse
import logging
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from PIL import Image

from summarize_resume import (
    build_parser as build_summary_parser,
    extract_text_from_pdf,
    maybe_copy,
    maybe_save,
    normalize_text,
    require_openai,
    sanitize_text,
    summarize_text,
    validate_inputs,
)
# スカウト媒体向けスカウトメール作成
from scout_mail import (
    DEFAULT_CANDIDATE_ACTION as DEFAULT_SCOUT_CANDIDATE_ACTION,
    DEFAULT_DESIRED_LOCATIONS as DEFAULT_SCOUT_DESIRED_LOCATIONS,
    DEFAULT_DESIRED_ROLES as DEFAULT_SCOUT_DESIRED_ROLES,
    DEFAULT_POSITION as DEFAULT_SCOUT_POSITION,
    DEFAULT_TONE as DEFAULT_SCOUT_TONE,
    DEFAULT_WORK_LOCATION as DEFAULT_SCOUT_WORK_LOCATION,
    ScoutMailRequest,
    generate_scout_mail,
    read_text_file,
)


LOG_PATH = Path(__file__).with_name("sharex_resume.log")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
PDF_EXTENSION = ".pdf"
DEFAULT_MIN_TEXT_CHARS = 200


@contextmanager
def timed_step(logger: logging.Logger, label: str):
    start = perf_counter()
    logger.info("開始: %s", label)
    try:
        yield
    finally:
        logger.info("処理時間: %s %.2f秒", label, perf_counter() - start)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("sharex_resume")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def build_parser() -> argparse.ArgumentParser:
    summary_parser = build_summary_parser()

    parser = argparse.ArgumentParser(
        description="ShareX のキャプチャ結果から、OCR・要約まで一括実行します。"
    )
    parser.add_argument("input_path", help="ShareX から渡される画像または PDF のパス")
    parser.add_argument(
        "--model",
        default=summary_parser.get_default("model"),
        help=f"使用するモデル名。既定値: {summary_parser.get_default('model')}",
    )
    parser.add_argument(
        "--prompt",
        default=summary_parser.get_default("prompt"),
        help="要約用のカスタムプロンプト。未指定時は summarize_resume.py の既定値を使います。",
    )
    parser.add_argument(
        "--save",
        help="要約結果を保存する .txt ファイルパス。未指定時は OCR PDF と同じ場所に保存します。",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="要約結果をクリップボードにもコピーします。",
    )
    parser.add_argument(
        "--scout-mail",
        action="store_true",
        help="要約結果をもとにスカウトメールも生成します。",
    )
    parser.add_argument(
        "--mail-save",
        help="スカウトメールを保存する .txt ファイルパス。未指定時は OCR PDF と同じ場所に保存します。",
    )
    parser.add_argument(
        "--copy-mail",
        action="store_true",
        help="生成したスカウトメールをクリップボードにもコピーします。",
    )
    parser.add_argument(
        "--company-name",
        default=os.getenv("SCOUT_COMPANY_NAME", ""),
        help="スカウトメールに入れる会社名。環境変数 SCOUT_COMPANY_NAME でも指定できます。",
    )
    parser.add_argument(
        "--position",
        default=os.getenv("SCOUT_POSITION", DEFAULT_SCOUT_POSITION),
        help="募集ポジション名。環境変数 SCOUT_POSITION でも指定できます。",
    )
    parser.add_argument(
        "--candidate-action",
        default=os.getenv("SCOUT_CANDIDATE_ACTION", DEFAULT_SCOUT_CANDIDATE_ACTION),
        help="候補者の媒体上アクション。既定値: 気になる",
    )
    parser.add_argument(
        "--desired-roles",
        default=os.getenv("SCOUT_DESIRED_ROLES", DEFAULT_SCOUT_DESIRED_ROLES),
        help="候補者の希望職種。既定値: 営業職",
    )
    parser.add_argument(
        "--desired-locations",
        default=os.getenv("SCOUT_DESIRED_LOCATIONS", DEFAULT_SCOUT_DESIRED_LOCATIONS),
        help="候補者の希望勤務地。既定値: 東京",
    )
    parser.add_argument(
        "--work-location",
        default=os.getenv("SCOUT_WORK_LOCATION", DEFAULT_SCOUT_WORK_LOCATION),
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
        "--mail-tone",
        default=os.getenv("SCOUT_TONE", DEFAULT_SCOUT_TONE),
        help="スカウトメールの文面トーン。環境変数 SCOUT_TONE でも指定できます。",
    )
    parser.add_argument(
        "--language",
        default="jpn",
        help="ocrmypdf に渡す OCR 言語。既定値: jpn",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="中間生成物の PDF を残します。",
    )
    parser.add_argument(
        "--min-text-chars",
        type=int,
        default=DEFAULT_MIN_TEXT_CHARS,
        help=(
            "PDFから抽出できたテキストを十分とみなす最小文字数。"
            f"既定値: {DEFAULT_MIN_TEXT_CHARS}"
        ),
    )
    return parser


def detect_input_kind(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix == PDF_EXTENSION:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS:
        return "image"

    supported = ", ".join(sorted([PDF_EXTENSION, *IMAGE_EXTENSIONS]))
    raise SystemExit(
        f"対応していない入力形式です: {input_path.suffix or '(拡張子なし)'}。"
        f"対応形式: {supported}"
    )


def build_output_base_path(input_path: Path) -> Path:
    if (
        input_path.suffix.lower() == PDF_EXTENSION
        and input_path.name.lower().endswith(".ocr.pdf")
    ):
        return input_path
    return input_path.with_name(f"{input_path.stem}.ocr.pdf")


def convert_to_pdf(input_path: Path, logger: logging.Logger) -> tuple[Path, bool]:
    if input_path.suffix.lower() == ".pdf":
        logger.info("入力は PDF のため、PDF 変換をスキップします: %s", input_path)
        return input_path, False

    output_pdf = input_path.with_suffix(".pdf")
    logger.info("画像を PDF に変換します: %s -> %s", input_path, output_pdf)

    with Image.open(input_path) as image:
        rgb_image = image.convert("RGB")
        rgb_image.save(output_pdf, "PDF")

    logger.info("PDF 変換が完了しました: %s", output_pdf)
    return output_pdf, True


def run_ocr(input_pdf: Path, language: str, logger: logging.Logger) -> Path:
    output_pdf = input_pdf.with_name(f"{input_pdf.stem}.ocr.pdf")
    exe_candidate = Path(sys.executable).with_name("ocrmypdf.exe")
    module_command = [
        sys.executable,
        "-m",
        "ocrmypdf",
        "--force-ocr",
        "--language",
        language,
        str(input_pdf),
        str(output_pdf),
    ]
    exe_command = [
        str(exe_candidate),
        "--force-ocr",
        "--language",
        language,
        str(input_pdf),
        str(output_pdf),
    ]

    if shutil.which("ocrmypdf"):
        command = [
            "ocrmypdf",
            "--force-ocr",
            "--language",
            language,
            str(input_pdf),
            str(output_pdf),
        ]
        logger.info("PATH 上の ocrmypdf を使用します")
    elif exe_candidate.exists():
        command = exe_command
        logger.info("venv 内の ocrmypdf.exe を使用します: %s", exe_candidate)
    else:
        command = module_command
        logger.info("python -m ocrmypdf を使用します: %s", sys.executable)

    logger.info("OCR を開始します: %s", " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    logger.info("ocrmypdf 終了コード: %s", result.returncode)
    if result.stdout.strip():
        logger.info("ocrmypdf stdout:\n%s", result.stdout.strip())
    if result.stderr.strip():
        logger.info("ocrmypdf stderr:\n%s", result.stderr.strip())

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "OCR に失敗しました。"
        if "OCR engine does not have language data" in message:
            raise SystemExit(
                "OCRエンジンに日本語の言語データが入っていません。"
                f"指定言語: {language}。"
                "Tesseract の日本語データを追加するか、--language eng のように利用可能な言語へ変更してください。"
            )
        raise SystemExit(f"ocrmypdf の実行に失敗しました: {message}")

    logger.info("OCR 済み PDF を生成しました: %s", output_pdf)
    return output_pdf


def find_tesseract_command(logger: logging.Logger) -> list[str]:
    command = shutil.which("tesseract")
    if command:
        logger.info("PATH 上の tesseract を使用します: %s", command)
        return [command]

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidate = Path(program_files) / "Tesseract-OCR" / "tesseract.exe"
    if candidate.exists():
        logger.info("Tesseract OCR の標準インストール先を使用します: %s", candidate)
        return [str(candidate)]

    raise SystemExit(
        "tesseract.exe が見つかりません。Tesseract OCR をインストールし、"
        "PATH に追加するか C:\\Program Files\\Tesseract-OCR\\tesseract.exe に配置してください。"
    )


def run_image_ocr(input_image: Path, language: str, logger: logging.Logger) -> str:
    command = [
        *find_tesseract_command(logger),
        str(input_image),
        "stdout",
        "-l",
        language,
    ]
    logger.info("画像OCRを開始します: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    logger.info("tesseract 終了コード: %s", result.returncode)
    if result.stderr.strip():
        logger.info("tesseract stderr:\n%s", result.stderr.strip())

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "画像OCRに失敗しました。"
        if "Error opening data file" in message or "Failed loading language" in message:
            raise SystemExit(
                "Tesseract に指定言語のデータが入っていません。"
                f"指定言語: {language}。"
                "jpn.traineddata を追加するか、--language eng のように利用可能な言語へ変更してください。"
            )
        raise SystemExit(f"画像OCRに失敗しました: {message}")

    text = normalize_text(result.stdout)
    if not text:
        raise SystemExit(f"画像からテキストを抽出できませんでした: {input_image}")
    logger.info("画像OCRテキスト文字数: %s", len(text))
    return f"[Page 1]\n{text}"


def try_extract_pdf_text(
    pdf_path: Path,
    min_text_chars: int,
    logger: logging.Logger,
) -> str:
    try:
        extracted_text = extract_text_from_pdf(pdf_path)
    except SystemExit as exc:
        logger.info("PDFテキスト抽出をスキップしてOCRへ進みます: %s", exc)
        return ""

    text_length = len(extracted_text.strip())
    logger.info("PDF抽出テキスト文字数: %s", text_length)
    if text_length < min_text_chars:
        logger.info(
            "PDF抽出テキストが閾値未満のためOCRへ進みます: %s < %s",
            text_length,
            min_text_chars,
        )
        return ""

    logger.info("PDFから十分なテキストを抽出できたためOCRをスキップします")
    return extracted_text


def extract_pdf_text_after_ocr(pdf_path: Path, min_text_chars: int, logger: logging.Logger) -> str:
    extracted_text = extract_text_from_pdf(pdf_path)
    text_length = len(extracted_text.strip())
    logger.info("OCR後PDF抽出テキスト文字数: %s", text_length)
    if text_length < min_text_chars:
        logger.info(
            "OCR後の抽出テキストが閾値未満です。取得できたテキストで処理を続行します: %s < %s",
            text_length,
            min_text_chars,
        )
    return extracted_text


def summarize_ocr_pdf(
    pdf_path: Path, model: str, prompt: str, logger: logging.Logger
) -> tuple[str, str, str]:
    logger.info("要約対象 PDF を検証します: %s", pdf_path)
    validate_inputs(pdf_path)

    logger.info("PDF からテキストを抽出します")
    extracted_text = extract_text_from_pdf(pdf_path)
    logger.info("抽出テキスト文字数: %s", len(extracted_text))

    summary_text, sanitized_text = summarize_extracted_text(
        extracted_text,
        model,
        prompt,
        logger,
    )
    return summary_text, extracted_text, sanitized_text


def summarize_extracted_text(
    extracted_text: str,
    model: str,
    prompt: str,
    logger: logging.Logger,
) -> tuple[str, str]:
    with timed_step(logger, "個人情報マスク"):
        logger.info("sanitize を実行します")
        sanitized_text = sanitize_text(extracted_text)
        logger.info("sanitize 後文字数: %s", len(sanitized_text))

    logger.info("OpenAI クライアントを初期化します")
    openai_class = require_openai()
    client = openai_class()

    with timed_step(logger, "経歴要約生成"):
        logger.info("OpenAI API に要約リクエストを送信します。model=%s", model)
        summary_text = summarize_text(client, model, prompt, sanitized_text)
        logger.info("要約取得完了。文字数: %s", len(summary_text))

    return summary_text, sanitized_text


def build_job_context(inline_context: str, context_file: str, logger: logging.Logger) -> str:
    file_context = read_text_file(context_file)
    if context_file:
        logger.info("求人補足情報ファイルを読み込みました: %s", context_file)
    return f"{inline_context}\n\n{file_context}".strip()


def generate_mail_from_summary(
    summary_text: str,
    sanitized_text: str,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> str:
    job_context = build_job_context(args.job_context, args.job_context_file, logger)
    request = ScoutMailRequest(
        candidate_summary=summary_text,
        sanitized_resume_text=sanitized_text,
        company_name=args.company_name,
        position=args.position,
        sender_name=args.sender_name,
        job_context=job_context,
        candidate_action=args.candidate_action,
        desired_roles=args.desired_roles,
        desired_locations=args.desired_locations,
        work_location=args.work_location,
        tone=args.mail_tone,
    )

    logger.info("OpenAI クライアントを初期化します（スカウトメール生成）")
    openai_class = require_openai()
    client = openai_class()

    with timed_step(logger, "スカウトメール生成"):
        logger.info("OpenAI API にスカウトメール生成リクエストを送信します。model=%s", args.model)
        scout_mail = generate_scout_mail(client, args.model, request)
        logger.info("スカウトメール取得完了。文字数: %s", len(scout_mail))
    return scout_mail


def main() -> None:
    logger = setup_logger()
    logger.info("========== ShareX OCR/要約 開始 ==========")
    overall_start = perf_counter()

    try:
        parser = build_parser()
        args = parser.parse_args()
        if args.copy_mail or args.mail_save:
            args.scout_mail = True
        logger.info(
            "引数: input_path=%s, model=%s, copy=%s, scout_mail=%s, copy_mail=%s, language=%s, save=%s, mail_save=%s, keep_intermediate=%s, min_text_chars=%s",
            args.input_path,
            args.model,
            args.copy,
            args.scout_mail,
            args.copy_mail,
            args.language,
            args.save,
            args.mail_save,
            args.keep_intermediate,
            args.min_text_chars,
        )

        with timed_step(logger, "入力判定"):
            input_path = Path(args.input_path).expanduser().resolve()
            logger.info("入力ファイル絶対パス: %s", input_path)
            if not input_path.exists():
                raise SystemExit(f"入力ファイルが見つかりません: {input_path}")
            if not input_path.is_file():
                raise SystemExit(f"ファイルではありません: {input_path}")
            input_kind = detect_input_kind(input_path)
            logger.info("入力形式: %s", input_kind)

        ocr_pdf_path: Path | None = None
        output_base_path = build_output_base_path(input_path)

        with timed_step(logger, "前処理"):
            if input_kind == "image":
                logger.info("画像入力のためPDF化をスキップし、直接OCRします")
                with timed_step(logger, "画像OCR"):
                    extracted_text = run_image_ocr(input_path, args.language, logger)
            else:
                with timed_step(logger, "PDFテキスト抽出"):
                    extracted_text = try_extract_pdf_text(
                        input_path,
                        args.min_text_chars,
                        logger,
                    )

                if extracted_text:
                    logger.info("PDF OCRをスキップします: %s", input_path)
                else:
                    with timed_step(logger, "PDF OCR"):
                        ocr_pdf_path = run_ocr(input_path, args.language, logger)
                    output_base_path = ocr_pdf_path
                    with timed_step(logger, "OCR済みPDFテキスト抽出"):
                        extracted_text = extract_pdf_text_after_ocr(
                            ocr_pdf_path,
                            args.min_text_chars,
                            logger,
                        )

        summary_text, sanitized_text = summarize_extracted_text(
            extracted_text,
            args.model,
            args.prompt,
            logger,
        )

        ocr_text_path = output_base_path.with_suffix(".ocrtext.txt")
        sanitized_text_path = output_base_path.with_suffix(".sanitized.txt")
        with timed_step(logger, "抽出テキスト保存"):
            logger.info("抽出テキストを保存します: %s", ocr_text_path)
            maybe_save(extracted_text, str(ocr_text_path))
            logger.info("sanitize 後テキストを保存します: %s", sanitized_text_path)
            maybe_save(sanitized_text, str(sanitized_text_path))

        output_txt = (
            Path(args.save) if args.save else output_base_path.with_suffix(".summary.txt")
        )
        with timed_step(logger, "要約保存"):
            logger.info("要約を保存します: %s", output_txt)
            maybe_save(summary_text, str(output_txt))

        if args.copy:
            logger.info("要約をクリップボードへコピーします")
        maybe_copy(summary_text, args.copy)

        scout_mail_text = ""
        mail_output_txt = None
        if args.scout_mail:
            scout_mail_text = generate_mail_from_summary(
                summary_text,
                sanitized_text,
                args,
                logger,
            )
            mail_output_txt = (
                Path(args.mail_save)
                if args.mail_save
                else output_base_path.with_suffix(".scout-mail.txt")
            )
            with timed_step(logger, "スカウトメール保存"):
                logger.info("スカウトメールを保存します: %s", mail_output_txt)
                maybe_save(scout_mail_text, str(mail_output_txt))

            if args.copy_mail:
                logger.info("スカウトメールをクリップボードへコピーします")
            maybe_copy(scout_mail_text, args.copy_mail)

        logger.info("処理が正常終了しました")
        print(summary_text)
        print(f"\n要約保存先: {output_txt}")
        if args.scout_mail:
            print("\n--- スカウトメール ---")
            print(scout_mail_text)
            print(f"\nスカウトメール保存先: {mail_output_txt}")
        if ocr_pdf_path:
            print(f"OCR PDF: {ocr_pdf_path}")
        else:
            print("OCR PDF: 生成なし（PDFテキスト抽出または画像直接OCR）")
    except Exception as exc:
        logger.exception("処理中にエラーが発生しました: %s", exc)
        print(
            "エラーが発生しました。詳細は "
            f"{LOG_PATH} を確認してください。"
        )
        raise
    finally:
        logger.info("処理時間: 全体 %.2f秒", perf_counter() - overall_start)
        logger.info("========== ShareX OCR/要約 終了 ==========\n")


if __name__ == "__main__":
    main()
