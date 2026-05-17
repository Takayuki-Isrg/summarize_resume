import re
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image


SHAREX_SCREENSHOTS_ROOT = Path.home() / "Documents" / "ShareX" / "Screenshots"
MONTH_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def resolve_output_dir(input_path: Path) -> Path:
    parent_dir = input_path.parent.resolve()
    sharex_root = SHAREX_SCREENSHOTS_ROOT.resolve()

    if parent_dir.parent == sharex_root and MONTH_DIR_PATTERN.fullmatch(parent_dir.name):
        return parent_dir

    file_month = datetime.fromtimestamp(input_path.stat().st_mtime).strftime("%Y-%m")
    return sharex_root / file_month


def main() -> None:
    if len(sys.argv) < 2:
        print("画像パスを指定してください")
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser().resolve()
    if not input_path.exists():
        print(f"画像ファイルが見つかりません: {input_path}")
        sys.exit(1)

    output_dir = resolve_output_dir(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{input_path.stem}.pdf"

    with Image.open(input_path) as img:
        img.convert("RGB").save(output_path, "PDF")

    print("PDF化完了:", output_path)


if __name__ == "__main__":
    main()
