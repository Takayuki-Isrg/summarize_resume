import sys
import os
from PIL import Image

if len(sys.argv) < 2:
    print("画像パスを指定してください")
    sys.exit()

input_path = sys.argv[1]

output_dir = r"G:\マイドライブ\ミイダス対応"
os.makedirs(output_dir, exist_ok=True)

base_name = os.path.splitext(os.path.basename(input_path))[0]
output_path = os.path.join(output_dir, base_name + ".pdf")

img = Image.open(input_path).convert("RGB")
img.save(output_path, "PDF")

print("PDF化完了:", output_path)