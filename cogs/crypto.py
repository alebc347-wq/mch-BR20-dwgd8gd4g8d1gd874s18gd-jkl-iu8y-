"""
編碼/解碼系統 Cog
支援 Base64, Base32, Hex, URL, ROT13, Unicode, Morse, Caesar, Binary 等 12+ 格式
"""

import discord
from discord import app_commands
from discord.ext import commands
import base64
import urllib.parse
import codecs
import html
from typing import Optional

from config import Colors
from utils.embeds import EmbedFactory


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Morse Code 編解碼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MORSE_CODE_DICT = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '1': '.----', '2': '..---', '3': '...--',
    '4': '....-', '5': '.....', '6': '-....', '7': '--...', '8': '---..',
    '9': '----.', '0': '-----', ' ': '/'
}
MORSE_REVERSE = {v: k for k, v in MORSE_CODE_DICT.items()}


def morse_encode(text: str) -> str:
    return " ".join(MORSE_CODE_DICT.get(c.upper(), '') for c in text)


def morse_decode(text: str) -> str:
    return "".join(MORSE_REVERSE.get(c, '') for c in text.split())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Caesar Cipher
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def caesar_shift(text: str, shift: int) -> str:
    result = ""
    for c in text:
        if c.isalpha():
            b = ord('A') if c.isupper() else ord('a')
            result += chr((ord(c) - b + shift) % 26 + b)
        else:
            result += c
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 編碼/解碼 函式表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ENCODE_FUNCS = {
    "base64": lambda t: base64.b64encode(t.encode()).decode(),
    "base32": lambda t: base64.b32encode(t.encode()).decode(),
    "base85": lambda t: base64.b85encode(t.encode()).decode(),
    "hex": lambda t: t.encode().hex(),
    "url": lambda t: urllib.parse.quote(t),
    "rot13": lambda t: codecs.encode(t, "rot_13"),
    "unicode": lambda t: "".join(f"\\u{ord(c):04x}" for c in t),
    "morse": morse_encode,
    "caesar": lambda t: caesar_shift(t, 3),
    "binary": lambda t: " ".join(format(ord(c), "08b") for c in t),
    "html_entities": lambda t: html.escape(t),
    "punycode": lambda t: t.encode("punycode").decode(),
}

DECODE_FUNCS = {
    "base64": lambda t: base64.b64decode(t).decode(),
    "base32": lambda t: base64.b32decode(t).decode(),
    "base85": lambda t: base64.b85decode(t).decode(),
    "hex": lambda t: bytes.fromhex(t).decode(),
    "url": lambda t: urllib.parse.unquote(t),
    "rot13": lambda t: codecs.decode(t, "rot_13"),
    "unicode": lambda t: t.encode().decode("unicode_escape"),
    "morse": morse_decode,
    "caesar": lambda t: caesar_shift(t, -3),
    "binary": lambda t: "".join(chr(int(b, 2)) for b in t.split()),
    "html_entities": lambda t: html.unescape(t),
    "punycode": lambda t: t.encode().decode("punycode"),
}

# 智能解碼使用的額外方法
import re
SMART_DECODERS = {
    "Base16": lambda s: base64.b16decode(s).decode("utf-8", errors="ignore"),
    "Base32": lambda s: base64.b32decode(s).decode("utf-8", errors="ignore"),
    "Base64": lambda s: base64.b64decode(s).decode("utf-8", errors="ignore"),
    "Base85": lambda s: base64.b85decode(s).decode("utf-8", errors="ignore"),
    "ROT13": lambda s: codecs.decode(s, "rot_13"),
    "ROT47": lambda s: ''.join([chr(33 + ((ord(c) - 33 + 47) % 94)) if 33 <= ord(c) <= 126 else c for c in s]),
    "URL Decode": lambda s: urllib.parse.unquote(s),
    "HTML Entity": lambda s: html.unescape(s),
    "Hex": lambda s: bytes.fromhex(s).decode("utf-8", errors="ignore"),
    "Binary": lambda s: ''.join([chr(int(b, 2)) for b in re.findall(r'[01]{8}', s)]),
    "Morse Code": morse_decode,
    "Caesar (-3)": lambda s: caesar_shift(s, -3),
    "Unicode Escape": lambda s: s.encode().decode("unicode_escape"),
    "反轉字串": lambda s: s[::-1],
    "Double Base64": lambda s: base64.b64decode(base64.b64decode(s)).decode("utf-8", errors="ignore"),
}


def try_convert(func, text: str):
    try:
        return func(text)
    except Exception:
        return None


def multi_steps(text: str, steps: str, funcs: dict) -> str:
    for step in steps.split(">"):
        func = funcs.get(step.strip().lower())
        if not func:
            return f"❌ 不支援的類型：{step}"
        try:
            text = func(text)
        except Exception:
            return f"❌ 轉換失敗：{step}"
    return text


def smart_decode(text: str) -> list[tuple[str, str]]:
    results = []
    for name, func in SMART_DECODERS.items():
        try:
            result = func(text)
            if result and result != text and 0 < len(result) < 1500:
                # 過濾無意義結果
                if any(c.isprintable() for c in result):
                    results.append((name, result.strip()))
        except Exception:
            pass
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Select Menu UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EncodeSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        options = [discord.SelectOption(label=name.upper(), value=name) for name in ENCODE_FUNCS.keys()]
        super().__init__(placeholder="🔽 選擇編碼類型", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"✅ 已選擇 **{self.values[0].upper()}** 編碼方式，請在此頻道貼上要編碼的內容：",
            ephemeral=True,
        )

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for("message", timeout=60, check=check)
        except Exception:
            await interaction.followup.send("⌛ 超時，請重新使用 `/encode` 指令", ephemeral=True)
            return

        content = msg.content
        result = try_convert(ENCODE_FUNCS[self.values[0]], content)
        if result:
            embed = discord.Embed(title="🔐 編碼結果", color=Colors.PRIMARY)
            embed.add_field(name=f"**類型：** {self.values[0].upper()}", value="", inline=False)
            embed.add_field(name="**原文**", value=f"```{content[:500]}```", inline=False)
            embed.add_field(name="**結果**", value=f"```{result[:1000]}```", inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ 編碼失敗！")


class DecodeSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        options = [discord.SelectOption(label=name.upper(), value=name) for name in DECODE_FUNCS.keys()]
        super().__init__(placeholder="🔽 選擇解碼類型", options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"✅ 已選擇 **{self.values[0].upper()}** 解碼方式，請在此頻道貼上要解碼的內容：",
            ephemeral=True,
        )

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for("message", timeout=60, check=check)
        except Exception:
            await interaction.followup.send("⌛ 超時，請重新使用 `/decode` 指令", ephemeral=True)
            return

        content = msg.content
        result = try_convert(DECODE_FUNCS[self.values[0]], content)
        if result:
            embed = discord.Embed(title="🔓 解碼結果", color=Colors.SUCCESS)
            embed.add_field(name=f"**類型：** {self.values[0].upper()}", value="", inline=False)
            embed.add_field(name="**原文**", value=f"```{content[:500]}```", inline=False)
            embed.add_field(name="**結果**", value=f"```{result[:1000]}```", inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ 解碼失敗！")


class EncodeView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)
        self.add_item(EncodeSelect(bot))


class DecodeView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=60)
        self.add_item(DecodeSelect(bot))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cog 主體
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Crypto(commands.Cog):
    """編碼/解碼系統 — Base64, Hex, Morse, Caesar 等"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="encode", description="文字編碼（支援 12+ 格式）")
    @app_commands.describe(
        text="(可選) 直接輸入文字",
        steps="(可選) 多層編碼，例如 base32>base64>unicode"
    )
    async def encode(self, interaction: discord.Interaction, text: Optional[str] = None, steps: Optional[str] = None):
        if steps and text:
            result = multi_steps(text, steps, ENCODE_FUNCS)
            embed = discord.Embed(title="🔐 多層編碼結果", color=Colors.PRIMARY)
            embed.add_field(name="**步驟**", value=f"`{steps}`", inline=False)
            embed.add_field(name="**原文**", value=f"```{text[:500]}```", inline=False)
            embed.add_field(name="**結果**", value=f"```{str(result)[:1000]}```", inline=False)
            await interaction.response.send_message(embed=embed)
        elif text:
            # 直接用 Base64 編碼
            result = try_convert(ENCODE_FUNCS["base64"], text)
            if result:
                embed = discord.Embed(title="🔐 編碼結果 (Base64)", color=Colors.PRIMARY)
                embed.add_field(name="**原文**", value=f"```{text[:500]}```", inline=False)
                embed.add_field(name="**結果**", value=f"```{result[:1000]}```", inline=False)
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(embed=EmbedFactory.error("編碼失敗"), ephemeral=True)
        else:
            await interaction.response.send_message(
                "📥 請選擇要使用的編碼方式：", view=EncodeView(self.bot), ephemeral=True
            )

    @app_commands.command(name="decode", description="文字解碼（支援 12+ 格式）")
    @app_commands.describe(
        text="(可選) 直接輸入文字",
        steps="(可選) 多層解碼，例如 base32>unicode"
    )
    async def decode(self, interaction: discord.Interaction, text: Optional[str] = None, steps: Optional[str] = None):
        if steps and text:
            result = multi_steps(text, steps, DECODE_FUNCS)
            embed = discord.Embed(title="🔓 多層解碼結果", color=Colors.SUCCESS)
            embed.add_field(name="**步驟**", value=f"`{steps}`", inline=False)
            embed.add_field(name="**原文**", value=f"```{text[:500]}```", inline=False)
            embed.add_field(name="**結果**", value=f"```{str(result)[:1000]}```", inline=False)
            await interaction.response.send_message(embed=embed)
        elif text:
            result = try_convert(DECODE_FUNCS["base64"], text)
            if result:
                embed = discord.Embed(title="🔓 解碼結果 (Base64)", color=Colors.SUCCESS)
                embed.add_field(name="**原文**", value=f"```{text[:500]}```", inline=False)
                embed.add_field(name="**結果**", value=f"```{result[:1000]}```", inline=False)
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(embed=EmbedFactory.error("解碼失敗"), ephemeral=True)
        else:
            await interaction.response.send_message(
                "📥 請選擇要使用的解碼方式：", view=DecodeView(self.bot), ephemeral=True
            )

    @app_commands.command(name="smart_decode", description="🧠 智能辨識與解碼文字")
    @app_commands.describe(text="輸入一串疑似加密/編碼的內容")
    async def smart_decode_cmd(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(thinking=True)
        results = smart_decode(text)

        if not results:
            await interaction.followup.send(embed=EmbedFactory.error("無法辨識", "無法識別或解碼輸入內容。"))
            return

        embed = discord.Embed(title="🧠 智能解碼結果", color=0x55CCFF)
        embed.description = f"找到 **{len(results)}** 種可能的解碼方式"
        for name, result in results[:8]:
            display = result[:200] + "..." if len(result) > 200 else result
            embed.add_field(name=f"🔍 {name}", value=f"```\n{display}\n```", inline=False)

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Crypto(bot))
