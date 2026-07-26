import requests
import re
import json

url = "https://www.cwa.gov.tw/Data/js/eq/15_eq.js"
r = requests.get(url)
if r.status_code == 200:
    content = r.text
    # 提取 JSON 字串： eq_json = { ... };
    match = re.search(r"eq_json\s*=\s*(\{.*?\});", content, re.DOTALL)
    if match:
        json_str = match.group(1)
        data = json.loads(json_str)
        print("KEYS:", data.keys())
        # 列印第一筆地震
        records = data.get("records", [])
        if records:
            print("FIRST RECORD KEYS:", records[0].keys())
            print(json.dumps(records[0], indent=2, ensure_ascii=False))
    else:
        print("COULD NOT EXTRACT JSON")
else:
    print("FAILED TO FETCH:", r.status_code)
