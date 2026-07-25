import sys
import os

def upload_file(file_path):
    import requests
    url = "https://catbox.moe/user/api.php"
    data = {
        "reqtype": "fileupload"
    }
    with open(file_path, "rb") as f:
        files = {
            "fileToUpload": (os.path.basename(file_path), f)
        }
        response = requests.post(url, data=data, files=files)
        if response.status_code == 200:
            return response.text.strip()
        else:
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload_to_catbox.py <file_path1> <file_path2> ...")
        sys.exit(1)
    
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        try:
            print(f"Uploading {path}...")
            url = upload_file(path)
            print(f"SUCCESS: {url}")
        except Exception as e:
            print(f"FAILED for {path}: {e}")
