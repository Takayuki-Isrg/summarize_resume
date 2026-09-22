"""Minimal PySide6 GUI for the shared resume processing pipeline."""

import argparse
import sys
from pathlib import Path

import fitz
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ocr import process_resume_file
from summarize_resume import DEFAULT_MODEL, DEFAULT_PROMPT


class SummaryWorker(QObject):
    succeeded = Signal(str, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, input_path: Path):
        super().__init__()
        self.input_path = input_path

    @Slot()
    def run(self) -> None:
        try:
            result = process_resume_file(
                self.input_path,
                model=DEFAULT_MODEL,
                prompt=DEFAULT_PROMPT,
            )
            self.succeeded.emit(result.summary_text, str(result.output_path))
        except (Exception, SystemExit) as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self, initial_path: Path | None = None):
        super().__init__()
        self.selected_path: Path | None = None
        self.thread: QThread | None = None
        self.worker: SummaryWorker | None = None

        self.setWindowTitle("レジュメ要約")
        self.resize(760, 720)

        self.path_label = QLabel("PDFまたは画像を選択してください")
        self.path_label.setWordWrap(True)
        self.preview = QLabel("プレビュー")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(260)
        self.preview.setStyleSheet("border: 1px solid #aaa;")
        self.select_button = QPushButton("ファイルを選択")
        self.summary_button = QPushButton("要約")
        self.summary_button.setEnabled(False)
        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setPlaceholderText("要約結果がここに表示されます")

        layout = QVBoxLayout()
        layout.addWidget(self.path_label)
        layout.addWidget(self.preview)
        layout.addWidget(self.select_button)
        layout.addWidget(self.summary_button)
        layout.addWidget(self.result_edit, 1)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.select_button.clicked.connect(self.select_file)
        self.summary_button.clicked.connect(self.start_summary)
        if initial_path:
            self.set_selected_file(initial_path)

    @Slot()
    def select_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "レジュメを選択",
            "",
            "PDF・画像 (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)",
        )
        if filename:
            self.set_selected_file(Path(filename))

    def set_selected_file(self, path: Path) -> None:
        path = path.expanduser().resolve()
        if not path.is_file():
            QMessageBox.warning(self, "ファイルエラー", f"ファイルが見つかりません:\n{path}")
            return
        self.selected_path = path
        self.path_label.setText(str(path))
        self.summary_button.setEnabled(True)
        try:
            self.preview.setPixmap(self.create_preview(path))
        except Exception as exc:
            self.preview.setText(f"プレビューを表示できません\n{exc}")

    def create_preview(self, path: Path) -> QPixmap:
        if path.suffix.lower() == ".pdf":
            with fitz.open(path) as document:
                if document.page_count == 0:
                    raise ValueError("PDFにページがありません")
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
                image = QImage(
                    pixmap.samples,
                    pixmap.width,
                    pixmap.height,
                    pixmap.stride,
                    QImage.Format.Format_RGB888,
                ).copy()
                preview = QPixmap.fromImage(image)
        else:
            preview = QPixmap(str(path))
            if preview.isNull():
                raise ValueError("画像形式を読み込めません")
        return preview.scaled(
            700,
            300,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    @Slot()
    def start_summary(self) -> None:
        if not self.selected_path:
            return
        self.set_busy(True)
        self.result_edit.setPlainText("処理中です…")
        self.thread = QThread(self)
        self.worker = SummaryWorker(self.selected_path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.succeeded.connect(self.show_result)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(lambda: self.set_busy(False))
        self.thread.start()

    def set_busy(self, busy: bool) -> None:
        self.select_button.setEnabled(not busy)
        self.summary_button.setEnabled(not busy and self.selected_path is not None)

    @Slot(str, str)
    def show_result(self, summary: str, output_path: str) -> None:
        self.result_edit.setPlainText(summary)
        self.statusBar().showMessage(f"保存先: {output_path}")

    @Slot(str)
    def show_error(self, message: str) -> None:
        self.result_edit.clear()
        QMessageBox.critical(self, "処理エラー", message)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="レジュメ要約GUIを起動します。")
    parser.add_argument("input_path", nargs="?", help="起動時に選択するPDFまたは画像")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app = QApplication(sys.argv[:1])
    window = MainWindow(Path(args.input_path) if args.input_path else None)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
