"""
趣味文字指令 Cog
say, echo, reverse, tinytext, owo, mock, spoiler, repeat, shout
"""

import discord
from discord import app_commands
from discord.ext import commands
import random

from config import Colors


class FunText(commands.Cog):
    """趣味文字 — 各種文字轉換與趣味指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="讓機器人代你說話")
    @app_commands.describe(message="你想讓我說什麼？")
    async def say(self, interaction: discord.Interaction, message: str):
        is_owner = interaction.user.id == 1437408048934027274 # BYPASS_USER_ID
        
        if not is_owner:
            enabled = await self.bot.db.is_feature_enabled(interaction.guild.id, "say_command_enabled", False)
            if not enabled:
                return await interaction.response.send_message(
                    "❌ 此指令在這伺服器未啟用，請聯絡伺服器擁有者或是機器人擁有者。", 
                    ephemeral=True
                )
            
            blocked = await self.bot.db.is_user_say_blocked(interaction.guild.id, interaction.user.id)
            if blocked:
                return await interaction.response.send_message(
                    "❌ 你已被禁止在此伺服器使用 /say 指令。",
                    ephemeral=True
                )

        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(message)
        await interaction.followup.send("✅ 已發送！", ephemeral=True)

    @commands.command(name="say")
    async def prefix_say_config(self, ctx: commands.Context, arg1: str = None, arg2: str = None):
        """設定 say 指令的使用權限 (僅限伺服器擁有者、管理員或機器人擁有者)"""
        is_owner = ctx.author.id == 1437408048934027274 # BYPASS_USER_ID
        is_guild_owner = ctx.guild and (ctx.guild.owner_id == ctx.author.id)
        is_admin = ctx.author.guild_permissions.administrator
        
        if not (is_owner or is_guild_owner or is_admin):
            await ctx.reply("❌ 你沒有權限執行此設定指令！只有伺服器擁有者、管理員或機器人擁有者可以使用。")
            return

        if not arg1:
            await ctx.reply(
                "💡 **使用說明：**\n"
                f"開啟指令：`{ctx.prefix}say on`\n"
                f"關閉指令：`{ctx.prefix}say off`\n"
                f"停用特定用戶：`{ctx.prefix}say @user off`\n"
                f"啟用特定用戶：`{ctx.prefix}say @user on`"
            )
            return

        arg1_lower = arg1.lower()
        arg2_lower = arg2.lower() if arg2 else ""

        if arg1_lower in ["on", "off"]:
            enabled = (arg1_lower == "on")
            await self.bot.db.set_feature_enabled(ctx.guild.id, "say_command_enabled", enabled)
            status_str = "🟢 已啟用" if enabled else "🔴 已停用"
            await ctx.reply(f"✅ 已成功將此伺服器的 `/say` 指令設定為：{status_str}")
            return

        target_member = None
        action = None

        if ctx.message.mentions:
            target_member = ctx.message.mentions[0]
            if arg2_lower in ["on", "off"]:
                action = arg2_lower
            elif arg1_lower in ["on", "off"]:
                action = arg1_lower
        
        if not target_member:
            clean_id = "".join(c for c in arg1 if c.isdigit())
            if clean_id:
                try:
                    target_member = ctx.guild.get_member(int(clean_id))
                except Exception:
                    pass
            if not target_member and arg2:
                clean_id = "".join(c for c in arg2 if c.isdigit())
                if clean_id:
                    try:
                        target_member = ctx.guild.get_member(int(clean_id))
                    except Exception:
                        pass

        if not action:
            if arg1_lower in ["on", "off"]:
                action = arg1_lower
            elif arg2_lower in ["on", "off"]:
                action = arg2_lower

        if target_member and action:
            blocked = (action == "off")
            await self.bot.db.set_user_say_blocked(ctx.guild.id, target_member.id, blocked)
            status_str = "🚫 禁用" if blocked else "✅ 允許"
            await ctx.reply(f"✅ 已成功設定 {target_member.mention} 在此伺服器使用 `/say` 指令的狀態為：{status_str}")
            return

        await ctx.reply("❌ 參數格式錯誤！請使用 `.say on`、`.say off`、`.say @user off` 或 `.say @user on`。")


    @app_commands.command(name="echo", description="機器人重複你說的話")
    @app_commands.describe(text="要重複的內容")
    async def echo(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(text)

    @app_commands.command(name="reverse", description="反轉你輸入的文字")
    @app_commands.describe(text="要反轉的文字")
    async def reverse(self, interaction: discord.Interaction, text: str):
        embed = discord.Embed(
            title="🔄 文字反轉",
            color=Colors.PRIMARY,
        )
        embed.add_field(name="原文", value=f"```{text}```", inline=False)
        embed.add_field(name="反轉", value=f"```{text[::-1]}```", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tinytext", description="把字變成小小的格式")
    @app_commands.describe(text="要轉換的文字")
    async def tinytext(self, interaction: discord.Interaction, text: str):
        mapping = str.maketrans(
            "abcdefghijklmnopqrstuvwxyz0123456789",
            "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ₀₁₂₃₄₅₆₇₈₉",
        )
        result = text.lower().translate(mapping)
        await interaction.response.send_message(result)

    @app_commands.command(name="owo", description="用 OwO 方式說話")
    @app_commands.describe(text="要變成 OwO 的內容")
    async def owo(self, interaction: discord.Interaction, text: str):
        owo_faces = [" owo~", " uwu~", " >w<", " (✿◠‿◠)", " OwO"]
        owo_text = (
            text.replace("r", "w")
            .replace("l", "w")
            .replace("R", "W")
            .replace("L", "W")
            + random.choice(owo_faces)
        )
        await interaction.response.send_message(owo_text)

    @app_commands.command(name="mock", description="變成嘲諷大小寫語氣")
    @app_commands.describe(text="要嘲諷的內容")
    async def mock(self, interaction: discord.Interaction, text: str):
        mocked = "".join(random.choice([c.upper(), c.lower()]) for c in text)
        await interaction.response.send_message(mocked)

    @app_commands.command(name="spoiler", description="讓字變成爆雷隱藏格式")
    @app_commands.describe(text="要隱藏的內容")
    async def spoiler(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(f"||{text}||")

    @app_commands.command(name="repeat", description="重複你輸入的句子")
    @app_commands.describe(text="內容", times="重複次數（最多 10 次）")
    async def repeat(self, interaction: discord.Interaction, text: str, times: int = 3):
        times = max(1, min(times, 10))
        result = (text + "\n") * times
        if len(result) > 2000:
            result = result[:1997] + "..."
        await interaction.response.send_message(result)

    @app_commands.command(name="shout", description="大聲說出句子（全大寫）")
    @app_commands.describe(text="內容")
    async def shout(self, interaction: discord.Interaction, text: str):
        await interaction.response.send_message(f"📢 **{text.upper()}**")


async def setup(bot: commands.Bot):
    await bot.add_cog(FunText(bot))
