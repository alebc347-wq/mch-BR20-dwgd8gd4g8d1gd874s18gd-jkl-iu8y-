"""
互動計算機 Cog
基本模式 + 科學模式，使用 AST 安全計算，Modal UI
"""

import discord
from discord import app_commands
from discord.ext import commands
import math
import ast

from config import Colors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 安全運算核心
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCIENTIFIC_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "round": round,
    "pow": pow,
}

SCIENTIFIC_NAMES = {
    "pi": math.pi,
    "e": math.e,
}

ALLOWED_BIN_OPS = (
    ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow,
)
ALLOWED_UNARY_OPS = (ast.UAdd, ast.USub)


def _safe_eval(node: ast.AST, scientific: bool) -> float:
    """對 AST 做安全的遞迴運算"""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, scientific)

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ALLOWED_UNARY_OPS):
        value = _safe_eval(node.operand, scientific)
        return +value if isinstance(node.op, ast.UAdd) else -value

    if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_BIN_OPS):
        left = _safe_eval(node.left, scientific)
        right = _safe_eval(node.right, scientific)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("除以零")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("除以零")
            return left // right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left ** right

    if scientific:
        if isinstance(node, ast.Name) and node.id in SCIENTIFIC_NAMES:
            return SCIENTIFIC_NAMES[node.id]

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in SCIENTIFIC_FUNCS:
                func = SCIENTIFIC_FUNCS[func_name]
                args = [_safe_eval(arg, scientific) for arg in node.args]
                return func(*args)

    raise ValueError("不支援的運算式或符號")


def calculate_expression(expr: str, scientific: bool) -> float:
    expr = expr.replace("^", "**")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        raise ValueError("運算式格式錯誤，請檢查括號與符號。")
    return _safe_eval(tree, scientific)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI 元件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CalcInputModal(discord.ui.Modal, title="🧮 輸入算式"):
    expression = discord.ui.TextInput(
        label="請輸入要計算的表達式",
        placeholder="例如：1+2*3 或 sqrt(2^2+3^2)",
        style=discord.TextStyle.short,
        required=True,
        max_length=200,
    )

    def __init__(self, view: "CalculatorView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        expr = self.expression.value.strip()

        try:
            result = calculate_expression(expr, self.view_ref.scientific)
            result_str = f"{result:.10g}"
            status = "✅ 計算成功"
            color = Colors.SUCCESS
        except ZeroDivisionError:
            result_str = "無法除以 0"
            status = "❌ 錯誤：除以 0"
            color = Colors.ERROR
        except OverflowError:
            result_str = "結果太大，超出範圍"
            status = "❌ 錯誤：溢位"
            color = Colors.ERROR
        except ValueError as e:
            result_str = str(e)
            status = "❌ 無效的運算式"
            color = Colors.ERROR

        mode_text = "進階模式（科學）" if self.view_ref.scientific else "基本模式（一般運算）"

        embed = discord.Embed(
            title="🧮 計算機",
            description=f"**模式：** {mode_text}",
            color=color,
        )
        embed.add_field(name="📥 輸入的算式", value=f"`{expr}`", inline=False)
        embed.add_field(name="📤 計算結果", value=f"```{result_str}```", inline=False)
        embed.set_footer(text="5 分鐘未使用將自動停止")

        try:
            await self.view_ref.message.edit(embed=embed, view=self.view_ref)
        except Exception:
            pass

        await interaction.response.send_message(status, ephemeral=True)


class CalculatorView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.scientific = False
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ 這不是你的計算機，請自己使用 `/calculator` 開一台。", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            try:
                embed = self.message.embeds[0] if self.message.embeds else None
                if embed:
                    embed.color = discord.Color.dark_grey()
                    embed.set_footer(text="⏹ 計算機已停止，請使用 /calculator 重新啟動。")
                    await self.message.edit(content="⏹ 計算機已停止。", embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="輸入算式", style=discord.ButtonStyle.primary, emoji="✏️")
    async def input_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CalcInputModal(self))

    @discord.ui.button(label="切換到進階模式", style=discord.ButtonStyle.secondary, emoji="📈")
    async def toggle_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.scientific = not self.scientific
        if self.scientific:
            button.label = "切換為基本模式"
            button.emoji = "📉"
            mode_text = "進階模式（科學）"
            desc = (
                "支援函式：`sqrt(x)`, `log(x)`, `sin(x)`, `cos(x)`, `tan(x)`, "
                "`abs(x)`, `round(x)`, `pow(a,b)`\n"
                "常數：`pi`, `e`\n"
                "也支援：+, -, *, /, //, %, **, ^, ()"
            )
        else:
            button.label = "切換到進階模式"
            button.emoji = "📈"
            mode_text = "基本模式（一般運算）"
            desc = (
                "支援：`+  -  *  /  //  %  **  ^  ()`\n"
                "`^` 會被當成次方，如 `2^3` = 8\n"
                "想用更多函式請切換到進階模式。"
            )

        embed = discord.Embed(
            title="🧮 計算機",
            description=f"**模式：** {mode_text}\n\n{desc}",
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="5 分鐘未使用將自動停止")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="說明 / 範例", style=discord.ButtonStyle.success, emoji="❔")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        examples = (
            "**基本模式範例：**\n"
            "`1+2*3`\n"
            "`(10-3)/2`\n"
            "`5//2`, `7%3`, `2^10`\n\n"
            "**進階模式範例：**\n"
            "`sqrt(2^2+3^2)`\n"
            "`log(10)`\n"
            "`sin(pi/2)`\n"
            "`pow(2, 8)`"
        )
        await interaction.response.send_message(examples, ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cog 主體
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Calculator(commands.Cog):
    """互動計算機 — 基本與科學模式"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="calculator", description="開啟互動計算機（支援基本與科學模式）")
    async def calculator(self, interaction: discord.Interaction):
        view = CalculatorView(user_id=interaction.user.id)

        desc = (
            "**模式：** 基本模式（一般運算）\n\n"
            "支援：`+  -  *  /  //  %  **  ^  ()`\n"
            "`^` 會被當成次方，如 `2^3` = 8\n"
            "按下 **✏️ 輸入算式** 開始計算。\n"
            "需要更多數學函式可按 **📈 切換到進階模式**。"
        )

        embed = discord.Embed(
            title="🧮 計算機",
            description=desc,
            color=Colors.PRIMARY,
        )
        embed.set_footer(text="5 分鐘未使用將自動停止")

        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        view.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(Calculator(bot))
