"""
緊急輕量化更新包打包工具 (Emergency Update Pack Builder)
自動打包核心程式碼 (main.py, cogs/, utils/, config.py 等)
排除 .git, data/, __pycache__, .env 與大型暫存檔，產生極小體積的 update_pack.zip
"""

import os
import sys
import zipfile

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', write_through=True)

OUTPUT_ZIP = "update_pack.zip"

# 需要包含的核心目錄與檔案
INCLUDE_FILES = ["main.py", "config.py", "requirements.txt", ".env.example"]
INCLUDE_DIRS = ["cogs", "utils"]

# 排除的檔案副檔名與名稱
EXCLUDE_EXTS = {".pyc", ".pyo", ".tmp", ".log", ".bak", ".swp", ".zip"}
EXCLUDE_DIRS = {"__pycache__", ".git", ".agents", "data", "tests", "scratch", ".github", ".gemini"}


def build_pack() -> str:
    root_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(root_dir, OUTPUT_ZIP)

    # 若舊的 zip 已存在，先移除
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass

    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # 1. 加入頂層重要檔案
        for fname in INCLUDE_FILES:
            fpath = os.path.join(root_dir, fname)
            if os.path.isfile(fpath):
                z.write(fpath, arcname=fname)
                file_count += 1

        # 2. 加入核心模組目錄
        for dname in INCLUDE_DIRS:
            dir_path = os.path.join(root_dir, dname)
            if not os.path.isdir(dir_path):
                continue
            for root, dirs, files in os.walk(dir_path):
                # 過濾排除目錄
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for file in files:
                    if os.path.splitext(file)[1].lower() in EXCLUDE_EXTS:
                        continue
                    if file.startswith("."):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, root_dir)
                    z.write(full_path, arcname=rel_path)
                    file_count += 1

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"✅ 更新包已生成：{OUTPUT_ZIP}")
    print(f"📦 包含檔案數：{file_count} 個")
    print(f"📊 檔案大小：{size_kb:.2f} KB")
    return zip_path


if __name__ == "__main__":
    build_pack()
