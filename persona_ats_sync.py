from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
DOWNLOADS_DIR = ROOT / "downloads"
SUMMARIES_DIR = ROOT / "summaries"
LOGS_DIR = ROOT / "logs"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "processed_documents.json"
LOG_FILE = LOGS_DIR / "persona_ats_sync.log"

DEFAULT_CANDIDATE_LIST_KEYS = ("items", "data", "candidates")
DEFAULT_DOCUMENT_LIST_KEYS = ("items", "data", "documents")
DEFAULT_CANDIDATE_ID_FIELDS = ("id", "candidate_id")
DEFAULT_DOCUMENT_ID_FIELDS = ("id", "document_id")
DEFAULT_DOWNLOAD_URL_PATHS = ("item.download_url", "data.download_url", "download_url")
DEFAULT_FILE_NAME_FIELDS = (
    "file_name",
    "filename",
    "original_filename",
    "name",
    "title",
)
DEFAULT_DOCUMENT_KEYWORDS = (
    "\u5c65\u6b74\u66f8",
    "\u8077\u52d9\u7d4c\u6b74\u66f8",
    "resume",
    "cv",
    "career",
)

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}\b")


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_env_file_without_dependency(path)
        return

    load_dotenv(path if path.exists() else None)


def load_env_file_without_dependency(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def setup_directories() -> None:
    for directory in (DOWNLOADS_DIR, SUMMARIES_DIR, LOGS_DIR, STATE_DIR):
        directory.mkdir(exist_ok=True)


def setup_logger() -> logging.Logger:
    setup_directories()

    logger = logging.getLogger("persona_ats_sync")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def parse_csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name, "")
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def scrub_for_log(value: Any) -> str:
    text = str(value)
    api_key = os.getenv("PERSONA_API_KEY")
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = EMAIL_RE.sub("[email]", text)
    text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", text)
    text = re.sub(r"(access_token=)[^&\s]+", r"\1[redacted]", text)
    return text


def safe_path_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned or "unknown"


def current_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(state: dict[str, Any]) -> None:
    setup_directories()
    tmp_path = STATE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATE_FILE)


def first_present(mapping: Any, fields: tuple[str, ...]) -> str | None:
    if not isinstance(mapping, dict):
        return None
    for field in fields:
        value = mapping.get(field)
        if value is not None and str(value).strip():
            return str(value)
    return None


def get_path(mapping: Any, dotted_path: str) -> Any:
    current = mapping
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def extract_collection(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_collection(value, keys)
            if nested:
                return nested

    return []


def extract_download_url(payload: Any, paths: tuple[str, ...]) -> str:
    for path in paths:
        value = get_path(payload, path)
        if value is not None and str(value).strip():
            return str(value)
    raise RuntimeError("download_url not found in document detail response")


def looks_like_target_document(
    document: dict[str, Any],
    file_name_fields: tuple[str, ...],
    keywords: tuple[str, ...],
    include_all: bool,
) -> bool:
    if include_all:
        return True

    haystack = " ".join(
        str(document.get(field, "")) for field in file_name_fields + ("document_type", "type")
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def build_candidate_params(raw_params: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for raw_param in raw_params:
        if "=" not in raw_param:
            raise SystemExit(f"Invalid --candidate-param value: {raw_param}")
        key, value = raw_param.split("=", 1)
        params[key] = value
    return params


@dataclass(frozen=True)
class Config:
    api_base_url: str
    api_key: str
    candidates_path: str
    documents_path_template: str
    document_detail_path_template: str
    request_timeout_seconds: int
    summarizer_timeout_seconds: int
    summary_model: str | None
    candidate_list_keys: tuple[str, ...]
    document_list_keys: tuple[str, ...]
    candidate_id_fields: tuple[str, ...]
    document_id_fields: tuple[str, ...]
    download_url_paths: tuple[str, ...]
    file_name_fields: tuple[str, ...]
    document_keywords: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Config":
        summary_model = os.getenv("SUMMARY_MODEL") or os.getenv("OPENAI_MODEL")
        return cls(
            api_base_url=require_env("PERSONA_API_BASE_URL").rstrip("/"),
            api_key=require_env("PERSONA_API_KEY"),
            candidates_path=os.getenv("PERSONA_CANDIDATES_PATH", "/candidates"),
            documents_path_template=os.getenv(
                "PERSONA_DOCUMENTS_PATH_TEMPLATE",
                "/candidates/{candidate_id}/documents",
            ),
            document_detail_path_template=os.getenv(
                "PERSONA_DOCUMENT_DETAIL_PATH_TEMPLATE",
                "/candidates/{candidate_id}/documents/{document_id}",
            ),
            request_timeout_seconds=int(os.getenv("PERSONA_REQUEST_TIMEOUT_SECONDS", "30")),
            summarizer_timeout_seconds=int(os.getenv("SUMMARY_TIMEOUT_SECONDS", "600")),
            summary_model=summary_model,
            candidate_list_keys=parse_csv_env(
                "PERSONA_CANDIDATE_LIST_KEYS",
                DEFAULT_CANDIDATE_LIST_KEYS,
            ),
            document_list_keys=parse_csv_env(
                "PERSONA_DOCUMENT_LIST_KEYS",
                DEFAULT_DOCUMENT_LIST_KEYS,
            ),
            candidate_id_fields=parse_csv_env(
                "PERSONA_CANDIDATE_ID_FIELDS",
                DEFAULT_CANDIDATE_ID_FIELDS,
            ),
            document_id_fields=parse_csv_env(
                "PERSONA_DOCUMENT_ID_FIELDS",
                DEFAULT_DOCUMENT_ID_FIELDS,
            ),
            download_url_paths=parse_csv_env(
                "PERSONA_DOWNLOAD_URL_PATHS",
                DEFAULT_DOWNLOAD_URL_PATHS,
            ),
            file_name_fields=parse_csv_env(
                "PERSONA_FILE_NAME_FIELDS",
                DEFAULT_FILE_NAME_FIELDS,
            ),
            document_keywords=parse_csv_env(
                "PERSONA_DOCUMENT_KEYWORDS",
                DEFAULT_DOCUMENT_KEYWORDS,
            ),
        )


class PersonaClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "x-api-key": config.api_key,
                "Accept": "application/json",
            }
        )

    def build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.config.api_base_url}/{path.lstrip('/')}"

    def get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = self.session.get(
            self.build_url(path),
            params=params,
            timeout=self.config.request_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"PERSONA API request failed: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("PERSONA API response was not JSON") from exc

    def list_candidates(self, params: dict[str, str]) -> list[dict[str, Any]]:
        payload = self.get_json(self.config.candidates_path, params=params)
        return extract_collection(payload, self.config.candidate_list_keys)

    def list_documents(self, candidate_id: str) -> list[dict[str, Any]]:
        path = self.config.documents_path_template.format(candidate_id=candidate_id)
        payload = self.get_json(path)
        return extract_collection(payload, self.config.document_list_keys)

    def document_detail(self, candidate_id: str, document_id: str) -> Any:
        path = self.config.document_detail_path_template.format(
            candidate_id=candidate_id,
            document_id=document_id,
        )
        return self.get_json(path)


def download_pdf(download_url: str, output_path: Path, timeout_seconds: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".pdf.tmp")

    try:
        with requests.get(download_url, stream=True, timeout=timeout_seconds) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"PDF download failed: HTTP {response.status_code}")
            with tmp_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)
    except RuntimeError:
        raise
    except requests.RequestException as exc:
        raise RuntimeError(f"PDF download request failed: {exc.__class__.__name__}") from None

    if tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("PDF download produced an empty file")

    tmp_path.replace(output_path)


def run_summarize_resume(
    pdf_path: Path,
    summary_path: Path,
    config: Config,
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "summarize_resume.py"),
        str(pdf_path),
        "--save",
        str(summary_path),
    ]
    if config.summary_model:
        command.extend(["--model", config.summary_model])

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=config.summarizer_timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(f"summarize_resume.py failed: exit={result.returncode}")

    if not summary_path.exists() or summary_path.stat().st_size == 0:
        raise RuntimeError("summarize_resume.py did not create a summary file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch PERSONA ATS documents and summarize them with summarize_resume.py."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print candidate_id, document_id, and file name without downloading PDFs.",
    )
    parser.add_argument(
        "--candidate-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Add a query parameter to the candidate list API. Can be repeated.",
    )
    parser.add_argument(
        "--all-documents",
        action="store_true",
        help="Process every document instead of filtering by resume-related keywords.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        help="Limit candidate count for testing.",
    )
    return parser


def process_documents(args: argparse.Namespace, config: Config, logger: logging.Logger) -> int:
    state = read_state()
    client = PersonaClient(config)
    candidate_params = build_candidate_params(args.candidate_param)

    candidates = client.list_candidates(candidate_params)
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]

    target_count = 0
    processed_count = 0
    failed_count = 0

    logger.info(
        "sync started dry_run=%s candidates=%s",
        args.dry_run,
        len(candidates),
    )

    for candidate in candidates:
        candidate_id = first_present(candidate, config.candidate_id_fields)
        if not candidate_id:
            logger.warning("candidate skipped because candidate_id was not found")
            continue

        try:
            documents = client.list_documents(candidate_id)
        except Exception as exc:
            logger.error(
                "document list failed candidate_id=%s error=%s",
                candidate_id,
                scrub_for_log(exc),
            )
            failed_count += 1
            continue

        for document in documents:
            document_id = first_present(document, config.document_id_fields)
            if not document_id:
                logger.warning("document skipped because document_id was not found")
                continue

            if not looks_like_target_document(
                document,
                config.file_name_fields,
                config.document_keywords,
                args.all_documents,
            ):
                continue

            state_key = f"{candidate_id}:{document_id}"
            if state.get(state_key, {}).get("status") == "done":
                continue

            file_name = first_present(document, config.file_name_fields) or "-"
            target_count += 1

            if args.dry_run:
                print(
                    f"candidate_id={candidate_id}\t"
                    f"document_id={document_id}\t"
                    f"file_name={file_name}"
                )
                continue

            safe_candidate_id = safe_path_part(candidate_id)
            safe_document_id = safe_path_part(document_id)
            pdf_path = DOWNLOADS_DIR / safe_candidate_id / f"{safe_document_id}.pdf"
            summary_path = SUMMARIES_DIR / safe_candidate_id / f"{safe_document_id}.summary.txt"

            logger.info(
                "processing started candidate_id=%s document_id=%s",
                candidate_id,
                document_id,
            )

            try:
                detail = client.document_detail(candidate_id, document_id)
                download_url = extract_download_url(detail, config.download_url_paths)
                download_pdf(download_url, pdf_path, config.request_timeout_seconds)
                run_summarize_resume(pdf_path, summary_path, config)

                state[state_key] = {
                    "status": "done",
                    "processed_at": current_timestamp(),
                    "pdf_path": str(pdf_path.relative_to(ROOT)),
                    "summary_path": str(summary_path.relative_to(ROOT)),
                }
                processed_count += 1
                logger.info(
                    "processing completed candidate_id=%s document_id=%s",
                    candidate_id,
                    document_id,
                )
                print(f"processed candidate_id={candidate_id} document_id={document_id}")
            except Exception as exc:
                state[state_key] = {
                    "status": "failed",
                    "last_attempt_at": current_timestamp(),
                    "error": scrub_for_log(exc),
                }
                failed_count += 1
                logger.error(
                    "processing failed candidate_id=%s document_id=%s error=%s",
                    candidate_id,
                    document_id,
                    scrub_for_log(exc),
                )
            finally:
                write_state(state)

    logger.info(
        "sync finished dry_run=%s targets=%s processed=%s failed=%s",
        args.dry_run,
        target_count,
        processed_count,
        failed_count,
    )
    if not args.dry_run:
        print(f"processed={processed_count} failed={failed_count}")
    return 1 if failed_count else 0


def main() -> None:
    load_env_file(ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args()
    logger = setup_logger()
    config = Config.from_env()
    raise SystemExit(process_documents(args, config, logger))


if __name__ == "__main__":
    main()
