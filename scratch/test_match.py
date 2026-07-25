import sys
import os

# Add parent directory to path so we can import config/cogs/etc.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cogs.auto_reply import DEFAULT_REPLIES

def test_builtin_matching(content: str):
    content = content.strip()
    if content in DEFAULT_REPLIES:
        return DEFAULT_REPLIES[content]
    return None

test_cases = [
    ("早", "早早早！今天精神看起來不錯喔！☀️"),
    ("早上好", None),
    ("早安", "早安呀！☀️ 太陽公公已經上班了，你也不能偷懶啦～"),
    ("昨晚太晚睡，今天早上爬不起來", None),
    ("幹", "冷靜冷靜 🤫 喝杯茶消消氣～"),
    ("你在幹嘛", None),
    ("讚", "👍 超讚der！你最棒！"),
    ("點讚", None),
    ("哈囉", "嗨嗨嗨～終於看到你啦！👋 你今天是不是特別帥（或美）？😆"),
    ("哈囉大家", None),
]

failed = False
for inp, expected in test_cases:
    result = test_builtin_matching(inp)
    if result != expected:
        print(f"FAIL: Input '{inp}' expected '{expected}', but got '{result}'")
        failed = True
    else:
        print(f"PASS: Input '{inp}' -> '{result}'")

if not failed:
    print("All tests passed successfully!")
else:
    sys.exit(1)
