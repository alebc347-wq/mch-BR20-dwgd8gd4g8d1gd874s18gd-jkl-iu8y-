import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"c:\Users\caleb\Desktop\程式\py\py\勇者2.0\cogs\music.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "voice" in line:
        print(f"{i:4d}: {line.strip()}")
