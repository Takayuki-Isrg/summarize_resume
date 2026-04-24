import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from summarize_resume import (
    build_parser as build_summary_parser,
    extract_text_from_pdf,
    maybe_copy,
    maybe_save,
    require_openai,
    sanitize_text,
    summarize_text,
    validate_inputs,
)


LOG_PATH = Path(__file__).with_name("sharex_resume.log")


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
        description="ShareX のキャプチャ結果を PDF 化し、OCR・要約まで一括実行します。"
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
        "--language",
        default="jpn",
        help="ocrmypdf に渡す OCR 言語。既定値: jpn",
    )
    parser.add_argument(
        "--keep-intermediate",
        action="store_true",
        help="中間生成物の PDF を残します。",
    )
    return parser


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


def summarize_ocr_pdf(
    pdf_path: Path, model: str, prompt: str, logger: logging.Logger
) -> tuple[str, str, str]:
    logger.info("要約対象 PDF を検証します: %s", pdf_path)
    validate_inputs(pdf_path)

    logger.info("PDF からテキストを抽出します")
    extracted_text = extract_text_from_pdf(pdf_path)
    logger.info("抽出テキスト文字数: %s", len(extracted_text))

    logger.info("sanitize を実行します")
    sanitized_text = sanitize_text(extracted_text)
    logger.info("sanitize 後文字数: %s", len(sanitized_text))

    logger.info("OpenAI クライアントを初期化します")
    openai_class = require_openai()
    client = openai_class()

    logger.info("OpenAI API に要約リクエストを送信します。model=%s", model)
    summary_text = summarize_text(client, model, prompt, sanitized_text)
    logger.info("要約取得完了。文字数: %s", len(summary_text))
    return summary_text, extracted_text, sanitized_text


def main() -> None:
    logger = setup_logger()
    logger.info("========== ShareX OCR/要約 開始 ==========")

    try:
        parser = build_parser()
        args = parser.parse_args()
        logger.info(
            "引数: input_path=%s, model=%s, copy=%s, language=%s, save=%s, keep_intermediate=%s",
            args.input_path,
            args.model,
            args.copy,
            args.language,
            args.save,
            args.keep_intermediate,
        )

        input_path = Path(args.input_path).expanduser().resolve()
        logger.info("入力ファイル絶対パス: %s", input_path)
        if not input_path.exists():
            raise SystemExit(f"入力ファイルが見つかりません: {input_path}")

        pdf_path, generated_pdf = convert_to_pdf(input_path, logger)
        ocr_pdf_path = run_ocr(pdf_path, args.language, logger)
        summary_text, extracted_text, sanitized_text = summarize_ocr_pdf(
            ocr_pdf_path, args.model, args.prompt, logger
        )

        ocr_text_path = ocr_pdf_path.with_suffix(".ocrtext.txt")
        sanitized_text_path = ocr_pdf_path.with_suffix(".sanitized.txt")
        logger.info("抽出テキストを保存します: %s", ocr_text_path)
        maybe_save(extracted_text, str(ocr_text_path))
        logger.info("sanitize 後テキストを保存します: %s", sanitized_text_path)
        maybe_save(sanitized_text, str(sanitized_text_path))

        output_txt = (
            Path(args.save) if args.save else ocr_pdf_path.with_suffix(".summary.txt")
        )
        logger.info("要約を保存します: %s", output_txt)
        maybe_save(summary_text, str(output_txt))

        if args.copy:
            logger.info("要約をクリップボードへコピーします")
        maybe_copy(summary_text, args.copy)

        if generated_pdf and not args.keep_intermediate and pdf_path.exists():
            logger.info("中間 PDF を削除します: %s", pdf_path)
            pdf_path.unlink()

        logger.info("処理が正常終了しました")
        print(summary_text)
        print(f"\n要約保存先: {output_txt}")
        print(f"OCR PDF: {ocr_pdf_path}")
    except Exception as exc:
        logger.exception("処理中にエラーが発生しました: %s", exc)
        print(
            "エラーが発生しました。詳細は "
            f"{LOG_PATH} を確認してください。"
        )
        raise
    finally:
        logger.info("========== ShareX OCR/要約 終了 ==========\n")


if __name__ == "__main__":
    main()
