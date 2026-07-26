import requests
import json

CWA_API_KEY = "CWA-B18C5BCE-BB65-4C62-AFAF-656A3ED67EB0"
url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}"

r = requests.get(url)
if r.status_code == 200:
    data = r.json()
    print("KEYS:", data.keys())
    print("RECORDS KEYS:", data.get("records", {}).keys())
    eqs = data.get("records", {}).get("Earthquake", [])
    print(f"FOUND {len(eqs)} EARTHQUAKES")
    if eqs:
        print(json.dumps(eqs[0], indent=2, ensure_ascii=False))
else:
    print(f"FAILED: {r.status_code}")
    print(r.text)
