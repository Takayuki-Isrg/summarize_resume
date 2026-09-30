import logging
from pathlib import Path
from unittest.mock import Mock, patch

from ocr import process_resume_file


def test_process_resume_file_reuses_pdf_pipeline_and_saves_summary(tmp_path):
    source = tmp_path / "resume.pdf"
    source.write_bytes(b"dummy")
    logger = logging.getLogger("test_process_resume_file")
    llm_client=Mock(),

    with (
        patch("ocr.try_extract_pdf_text", return_value="[Page 1]\n経歴"),
        patch("ocr.summarize_extracted_text", return_value=("要約結果", "経歴")),
    ):
        result = process_resume_file(
            source,
            model="test-model",
            prompt="test-prompt",
            llm_client=llm_client,
            logger=logger,
        )

    assert result.summary_text == "要約結果"
    assert result.output_path == Path(tmp_path / "resume.ocr.summary.txt")
    assert result.output_path.read_text(encoding="utf-8") == "要約結果"
