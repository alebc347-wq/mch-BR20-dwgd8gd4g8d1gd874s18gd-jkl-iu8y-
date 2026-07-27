import os
import time
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from config import Colors

class RoleClaim(commands.Cog):
    """自訂身分組領取系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="gro", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def gro(self, ctx: commands.Context, role: discord.Role, *, description: str = None):
        """建立身分組領取面板 (.gro @身分組 [自訂說明文字])"""
        await ctx.message.delete()

        # 檢查機器人身分組階層是否足夠
        if ctx.guild.me.top_role <= role:
            return await ctx.send(f"❌ 機器人最高身分組階級必須高於 {role.name} 才能建立領取按鈕！", delete_after=5)

        if not description:
            description = "點擊下方按鈕以領取或取消對應的身分組："

        embed = discord.Embed(
            title="🏷️ 身分組領取中心",
            description=f"{description}\n\n• {role.mention}",
            color=role.color if role.color != discord.Color.default() else Colors.PRIMARY
        )
        
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=role.name,
            custom_id=f"claim_role_{role.id}",
            emoji="🏷️"
        )
        view.add_item(btn)

        await ctx.send(embed=embed, view=view)

    @gro.command(name="a")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def add_role(self, ctx: commands.Context, role: discord.Role):
        """新增身分組按鈕到現有的領取面板 (.gro a @身分組)"""
        await ctx.message.delete()

        # 檢查機器人身分組階層是否足夠
        if ctx.guild.me.top_role <= role:
            return await ctx.send(f"❌ 機器人最高身分組階級必須高於 {role.name} 才能建立領取按鈕！", delete_after=5)

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

        target_custom_id = f"claim_role_{role.id}"
        existing_role_ids = []
        view = discord.ui.View(timeout=None)

        # 重新建立現有的按鈕
        for row in found_msg.components:
            for item in row.children:
                if item.custom_id and item.custom_id.startswith("claim_role_"):
                    r_id = int(item.custom_id.replace("claim_role_", ""))
                    existing_role_ids.append(r_id)
                    btn = discord.ui.Button(
                        style=item.style,
                        label=item.label,
                        custom_id=item.custom_id,
                        emoji=item.emoji
                    )
                    view.add_item(btn)

        if role.id in existing_role_ids:
            return await ctx.send(f"⚠️ 身分組 {role.name} 已經在領取列表中了！", delete_after=5)

        if len(view.children) >= 25:
            return await ctx.send("❌ 該訊息的領取按鈕已達上限（25 個）！", delete_after=5)

        # 新增按鈕
        new_btn = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=role.name,
            custom_id=target_custom_id,
            emoji="🏷️"
        )
        view.add_item(new_btn)

        # 更新 Embed 說明
        embed = found_msg.embeds[0]
        desc = embed.description or ""
        if f"• {role.mention}" not in desc:
            embed.description = desc + f"\n• {role.mention}"

        await found_msg.edit(embed=embed, view=view)
        await ctx.send(f"✅ 已成功將 {role.name} 新增至領取列表！", delete_after=5)

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
            
        role_id_str = custom_id.replace("claim_role_", "")
        if not role_id_str.isdigit():
            return
            
        role_id = int(role_id_str)
        guild = interaction.guild
        if not guild:
            return
            
        role = guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message("❌ 找不到該身分組，可能已被刪除。", ephemeral=True)
            
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
            
        # 2. 檢查機器人的最高身分組是否比目標身分組高，否則無法操作
        if guild.me.top_role <= role:
            return await interaction.response.send_message(
                "❌ 權限不足：機器人的最高身分組必須高於該身分組才能進行操作，請聯絡管理員調整身分組順序。", 
                ephemeral=True
            )
            
        # 3. 領取 / 移除身分組
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
