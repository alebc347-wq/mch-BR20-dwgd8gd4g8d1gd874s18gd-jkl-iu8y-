import os
import time
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from config import Colors

STYLE_MAP = {
    "blue": discord.ButtonStyle.primary,
    "primary": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "gray": discord.ButtonStyle.secondary,
    "secondary": discord.ButtonStyle.secondary,
    "green": discord.ButtonStyle.success,
    "success": discord.ButtonStyle.success,
    "red": discord.ButtonStyle.danger,
    "danger": discord.ButtonStyle.danger,
}

def build_custom_id(role_id: int, required_role_id: int = None) -> str:
    """
    建立按鈕的 custom_id。
    格式：claim_role_{role_id}                              （無前置身份組）
          claim_role_{role_id}__req_{required_role_id}      （有前置身份組）
    """
    if required_role_id:
        return f"claim_role_{role_id}__req_{required_role_id}"
    return f"claim_role_{role_id}"

def parse_custom_id(custom_id: str):
    """
    解析 custom_id，回傳 (role_id, required_role_id)。
    required_role_id 為 None 表示無前置限制。
    """
    if "__req_" in custom_id:
        parts = custom_id.split("__req_")
        role_id_str = parts[0].replace("claim_role_", "")
        req_id_str = parts[1]
        if role_id_str.isdigit() and req_id_str.isdigit():
            return int(role_id_str), int(req_id_str)
        return None, None
    else:
        role_id_str = custom_id.replace("claim_role_", "")
        if role_id_str.isdigit():
            return int(role_id_str), None
        return None, None

class RoleClaim(commands.Cog):
    """自訂身分組領取系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="gro", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def gro(self, ctx: commands.Context, roles: commands.Greedy[discord.Role], *, description_or_color: str = None):
        """建立身分組領取面板
        
        用法：.gro @身分組1 [@身分組2 ...] [顏色] [說明文字]
             .gro @身分組1 --req @前置身份組 [顏色] [說明文字]
        
        使用 --req @身份組 可限制只有擁有指定身份組的人才能領取。
        """
        await ctx.message.delete()

        if not roles:
            return await ctx.send(
                "❌ 請提供至少一個有效的身分組！\n💡 使用格式：`.gro @身分組1 [@身分組2 ...] [顏色] [說明文字]`\n💡 限制資格：加入 `--req @前置身份組` 可設定前置身份組要求",
                delete_after=7
            )

        # 檢查機器人身分組階層是否足夠
        for r in roles:
            if ctx.guild.me.top_role <= r:
                return await ctx.send(f"❌ 機器人最高身分組階級必須高於 {r.name} 才能建立領取按鈕！", delete_after=5)

        # --- 解析 --req 參數 ---
        required_role: discord.Role = None
        remaining = description_or_color or ""

        if "--req" in remaining:
            req_parts = remaining.split("--req", 1)
            remaining = req_parts[0].strip()
            req_str = req_parts[1].strip()
            req_id_str = req_str.split()[0] if req_str else ""
            req_id_str = req_id_str.strip("<@&>")
            if req_id_str.isdigit():
                required_role = ctx.guild.get_role(int(req_id_str))
                if not required_role:
                    return await ctx.send("❌ 找不到 `--req` 所指定的身份組，請確認是否正確！", delete_after=5)

        style = discord.ButtonStyle.primary
        description = "點擊下方按鈕以領取或取消對應的身分組："

        if remaining:
            parts = remaining.split(maxsplit=1)
            first_word = parts[0].lower()
            if first_word in STYLE_MAP:
                style = STYLE_MAP[first_word]
                if len(parts) > 1:
                    description = parts[1]
            else:
                description = remaining

        # 建立身分組提及列表
        role_mentions = "\n".join([f"• {r.mention}" for r in roles])
        req_hint = f"\n\n🔒 **需要擁有 {required_role.mention} 才能領取**" if required_role else ""

        embed = discord.Embed(
            title="🏷️ 身分組領取中心",
            description=f"{description}{req_hint}\n\n{role_mentions}",
            color=roles[0].color if roles[0].color != discord.Color.default() else Colors.PRIMARY
        )

        view = discord.ui.View(timeout=None)
        for r in roles:
            btn = discord.ui.Button(
                style=style,
                label=r.name,
                custom_id=build_custom_id(r.id, required_role.id if required_role else None),
                emoji="🏷️"
            )
            view.add_item(btn)

        await ctx.send(embed=embed, view=view)

    @gro.command(name="a")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx: commands.Context, roles: commands.Greedy[discord.Role], *, options: str = "blue"):
        """新增身分組按鈕到現有的領取面板
        
        用法：.gro a @身分組1 [@身分組2 ...] [顏色]
             .gro a @身分組1 --req @前置身份組 [顏色]
        
        使用 --req @身份組 可限制只有擁有指定身份組的人才能領取。
        """
        await ctx.message.delete()

        if not roles:
            return await ctx.send(
                "❌ 請提供至少一個要新增的有效身分組！\n💡 使用格式：`.gro a @身分組1 [@身分組2 ...] [顏色]`\n💡 限制資格：加入 `--req @前置身份組` 可設定前置身份組要求",
                delete_after=7
            )

        # 檢查機器人身分組階層是否足夠
        for r in roles:
            if ctx.guild.me.top_role <= r:
                return await ctx.send(f"❌ 機器人最高身分組階級必須高於 {r.name} 才能建立領取按鈕！", delete_after=5)

        # --- 解析 --req 參數 ---
        required_role: discord.Role = None
        remaining = options or "blue"

        if "--req" in remaining:
            req_parts = remaining.split("--req", 1)
            remaining = req_parts[0].strip() or "blue"
            req_str = req_parts[1].strip()
            req_id_str = req_str.split()[0] if req_str else ""
            req_id_str = req_id_str.strip("<@&>")
            if req_id_str.isdigit():
                required_role = ctx.guild.get_role(int(req_id_str))
                if not required_role:
                    return await ctx.send("❌ 找不到 `--req` 所指定的身份組，請確認是否正確！", delete_after=5)

        color_lower = remaining.strip().lower()
        if color_lower not in STYLE_MAP:
            color_lower = "blue"
        style = STYLE_MAP[color_lower]

        # 尋找最近的領取面板訊息
        found_msg = None
        async with ctx.typing():
            async for message in ctx.channel.history(limit=50):
                if message.author.id == self.bot.user.id and message.embeds:
                    embed = message.embeds[0]
                    if embed.title == "🏷️ 身分組領取中心" and message.components:
                        has_claim_btn = False
                        for row in message.components:
                            for item in row.children:
                                if item.custom_id and item.custom_id.startswith("claim_role_"):
                                    has_claim_btn = True
                                    break
                        if has_claim_btn:
                            found_msg = message
                            break

        if not found_msg:
            return await ctx.send("❌ 找不到在此頻道發送的「身分組領取中心」訊息！", delete_after=5)

        existing_role_ids = []
        view = discord.ui.View(timeout=None)

        # 重新建立現有的按鈕（保留原 custom_id，維持舊的前置身份組設定）
        for row in found_msg.components:
            for item in row.children:
                if item.custom_id and item.custom_id.startswith("claim_role_"):
                    r_id, _ = parse_custom_id(item.custom_id)
                    if r_id:
                        existing_role_ids.append(r_id)
                    btn = discord.ui.Button(
                        style=item.style,
                        label=item.label,
                        custom_id=item.custom_id,
                        emoji=item.emoji
                    )
                    view.add_item(btn)

        new_added_roles = []
        for r in roles:
            if r.id in existing_role_ids:
                continue
            if len(view.children) >= 25:
                await ctx.send("❌ 該訊息的領取按鈕已達上限（25 個），部分身分組未加入！", delete_after=5)
                break

            new_btn = discord.ui.Button(
                style=style,
                label=r.name,
                custom_id=build_custom_id(r.id, required_role.id if required_role else None),
                emoji="🏷️"
            )
            view.add_item(new_btn)
            new_added_roles.append(r)

        if not new_added_roles:
            return await ctx.send("⚠️ 所有指定的身分組都已在列表中，或按鈕數已達上限！", delete_after=5)

        # 更新 Embed 說明與按鈕
        embed = found_msg.embeds[0]
        desc = embed.description or ""
        for r in new_added_roles:
            if f"• {r.mention}" not in desc:
                desc += f"\n• {r.mention}"

        # 若有前置身份組要求，在說明中追加提示
        if required_role:
            req_note = f"🔒 **需要擁有 {required_role.mention} 才能領取**"
            if req_note not in desc:
                desc = req_note + "\n" + desc
        embed.description = desc

        await found_msg.edit(embed=embed, view=view)
        added_names = ", ".join([r.name for r in new_added_roles])
        req_info = f"（需要身份組：{required_role.name}）" if required_role else ""
        await ctx.send(f"✅ 已成功新增身分組：{added_names} 至領取列表！{req_info}", delete_after=5)

    @gro.command(name="c", aliases=["color", "style"])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def change_color(self, ctx: commands.Context, roles: commands.Greedy[discord.Role], color: str):
        """編輯按鈕的顏色 (.gro c @身分組1 [@身分組2 ...] 顏色)"""
        await ctx.message.delete()
        
        if not roles:
            return await ctx.send(
                "❌ 請提供至少一個要修改顏色的有效身分組！\n💡 使用格式：`.gro c @身分組1 [@身分組2 ...] 顏色`",
                delete_after=7
            )

        color_lower = color.lower()
        if color_lower not in STYLE_MAP:
            return await ctx.send(
                "❌ 無效的顏色！可用的顏色為：`blue` (藍色), `grey` (灰色), `green` (綠色), `red` (紅色)。",
                delete_after=5
            )
            
        style = STYLE_MAP[color_lower]
        
        # 尋找最近的領取面板訊息
        found_msg = None
        async with ctx.typing():
            async for message in ctx.channel.history(limit=50):
                if message.author.id == self.bot.user.id and message.embeds:
                    embed = message.embeds[0]
                    if embed.title == "🏷️ 身分組領取中心" and message.components:
                        has_claim_btn = False
                        for row in message.components:
                            for item in row.children:
                                if item.custom_id and item.custom_id.startswith("claim_role_"):
                                    has_claim_btn = True
                                    break
                        if has_claim_btn:
                            found_msg = message
                            break

        if not found_msg:
            return await ctx.send("❌ 找不到在此頻道發送的「身分組領取中心」訊息！", delete_after=5)

        target_ids = [r.id for r in roles]
        view = discord.ui.View(timeout=None)
        updated_count = 0

        # 重新建立按鈕並修改目標按鈕顏色
        for row in found_msg.components:
            for item in row.children:
                if item.custom_id and item.custom_id.startswith("claim_role_"):
                    r_id, _ = parse_custom_id(item.custom_id)

                    if r_id in target_ids:
                        btn_style = style
                        updated_count += 1
                    else:
                        btn_style = item.style
                        
                    btn = discord.ui.Button(
                        style=btn_style,
                        label=item.label,
                        custom_id=item.custom_id,
                        emoji=item.emoji
                    )
                    view.add_item(btn)

        if updated_count == 0:
            return await ctx.send("❌ 指定的身分組按鈕均不存在於該面板上！", delete_after=5)

        await found_msg.edit(view=view)
        await ctx.send(f"✅ 已成功將 {updated_count} 個身分組按鈕顏色更新為 `{color_lower}`！", delete_after=5)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("claim_role_"):
            return

        # 1. 確保只有運行中的節點回應
        if not getattr(self.bot, "is_active_node", True):
            return

        role_id, required_role_id = parse_custom_id(custom_id)
        if role_id is None:
            return

        guild = interaction.guild
        if not guild:
            return

        role = guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message("❌ 找不到該身分組，可能已被刪除。", ephemeral=True)

        member = interaction.user
        if not isinstance(member, discord.Member):
            return

        # 2. 檢查前置身份組資格
        if required_role_id:
            required_role = guild.get_role(required_role_id)
            if not required_role:
                return await interaction.response.send_message(
                    "❌ 前置身份組不存在，可能已被刪除，請聯絡管理員。",
                    ephemeral=True
                )
            if required_role not in member.roles:
                return await interaction.response.send_message(
                    f"❌ 你沒有資格領取此身分組！\n🔒 需要擁有 **{required_role.name}** 身份組才能領取。",
                    ephemeral=True
                )

        # 3. 檢查機器人的最高身分組是否比目標身分組高，否則無法操作
        if guild.me.top_role <= role:
            return await interaction.response.send_message(
                "❌ 權限不足：機器人的最高身分組必須高於該身分組才能進行操作，請聯絡管理員調整身分組順序。",
                ephemeral=True
            )

        # 4. 領取 / 移除身分組
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="自訂身分組領取系統：取消領取")
                await interaction.response.send_message(f"✅ 已成功移除身分組：**{role.name}**", ephemeral=True)
            else:
                await member.add_roles(role, reason="自訂身分組領取系統：領取身分組")
                await interaction.response.send_message(f"✅ 已成功領取身分組：**{role.name}**", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 機器人權限不足，無法變更您的身分組。", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 變更身分組時發生未知錯誤：{e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RoleClaim(bot))
