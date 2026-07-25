"""
金主排行榜系統 Cog
提供自動建立「💴｜金主排行榜」頻道與「【💵】金主」身分組、
管理金主順序與留言、並即時更新精美排行榜 Embed 的功能。
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

from config import Colors, Emoji, BadgeImages
from utils.embeds import EmbedFactory


class SponsorSystem(commands.Cog):
    """金主排行榜管理系統"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 核心輔助方法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def update_leaderboard_message(self, guild: discord.Guild) -> bool:
        """重新渲染並更新/發送金主排行榜訊息"""
        # 1. 取得設定
        settings = await self.db.get_sponsor_settings(guild.id)
        if not settings or not settings.get('channel_id'):
            return False
            
        channel = guild.get_channel(settings['channel_id'])
        if not channel:
            return False
            
        # 2. 取得所有金主名單
        sponsors = await self.db.get_sponsors(guild.id)
        
        # 3. 建立精美的 Embed
        embed = discord.Embed(
            title="💴 ｜ 金主排行榜",
            description="感謝以下各位金主對本伺服器的無私奉獻與大力支持！✨\n我們的成長與成就離不開您的每一份心意！💖\n\n",
            color=0xF1C40F, # 金黃色
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=BadgeImages.SPONSOR)
        
        desc_lines = []
        valid_uids = []
        
        # 循序整理名單
        for idx, sub in enumerate(sponsors, 1):
            member = guild.get_member(sub['user_id'])
            if not member:
                # 成員已退群，自動清理
                await self.db.remove_sponsor(guild.id, sub['user_id'])
                continue
                
            valid_uids.append(sub['user_id'])
            note = sub['note'] if sub['note'] else "感謝無私奉獻！💖"
            
            # 前三名使用王冠/金銀銅牌
            if idx == 1:
                rank_str = "👑 **第一名**"
            elif idx == 2:
                rank_str = "🥈 **第二名**"
            elif idx == 3:
                rank_str = "🥉 **第三名**"
            else:
                rank_str = f"✨ **第 {idx} 名**"
                
            desc_lines.append(
                f"{rank_str} ｜ {member.mention}\n"
                f"↳ ✧ *{note}* ✧\n"
                f"───────────────────"
            )
            
        if not desc_lines:
            embed.description += "*目前排行榜上還沒有金主，期待您的加入！*"
        else:
            embed.description += "\n".join(desc_lines)
            
        embed.set_footer(text=f"本伺服器共有 {len(valid_uids)} 位金主 ｜ 隨時更新", icon_url=self.bot.user.display_avatar.url)
        
        # 4. 更新或發送訊息
        msg = None
        if settings.get('message_id'):
            try:
                msg = await channel.fetch_message(settings['message_id'])
                await msg.edit(embed=embed)
            except discord.NotFound:
                # 原本的訊息不存在（可能被刪了），重新發送
                msg = await channel.send(embed=embed)
                await self.db.set_sponsor_settings(guild.id, channel.id, msg.id)
        else:
            msg = await channel.send(embed=embed)
            await self.db.set_sponsor_settings(guild.id, channel.id, msg.id)
            
        return True

    async def sync_sponsors_and_roles(self, guild: discord.Guild):
        """雙向同步 Discord 身分組與資料庫"""
        role = discord.utils.get(guild.roles, name="【💵】金主")
        if not role:
            return
            
        # 1. 獲取目前已在資料庫的金主
        sponsors = await self.db.get_sponsors(guild.id)
        db_uids = [s['user_id'] for s in sponsors]
        
        # 2. 遍歷伺服器中擁有該身分組的成員，若不在資料庫中則補上
        for m in role.members:
            if m.id not in db_uids:
                await self.db.add_sponsor(guild.id, m.id, "感謝大力支持！💖")
                db_uids.append(m.id)
                
        # 3. 遍歷資料庫金主，若沒有身分組則補發
        for sub in sponsors:
            m = guild.get_member(sub['user_id'])
            if m and role not in m.roles:
                try:
                    await m.add_roles(role, reason="金主排行榜資料庫同步")
                except discord.Forbidden:
                    pass

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Slash Commands (指令群組)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(name="sponsor", description="金主排行榜管理系統")
    @app_commands.choices(action=[
        app_commands.Choice(name="初始化設定 (setup)", value="setup"),
        app_commands.Choice(name="新增金主 (add)", value="add"),
        app_commands.Choice(name="移除金主 (remove)", value="remove"),
        app_commands.Choice(name="調整順序 (move)", value="move"),
        app_commands.Choice(name="編輯留言 (edit)", value="edit"),
        app_commands.Choice(name="手動整理 (update)", value="update"),
    ])
    @app_commands.describe(
        action="要執行的動作",
        member="要管理的成員（新增、移除、移動或編輯留言時必填）",
        position="移動的目標順序（1 代表第一名，移動時必填）",
        note="感謝語或金額註記（新增/編輯時可填寫）"
    )
    async def sponsor_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        member: discord.Member = None,
        position: int = None,
        note: str = None
    ):
        guild = interaction.guild
        guild_id = guild.id
        
        if action == "setup":
            await interaction.response.defer(ephemeral=True)
            
            # 1. 建立身分組
            role = discord.utils.get(guild.roles, name="【💵】金主")
            role_created = False
            if not role:
                try:
                    role = await guild.create_role(
                        name="【💵】金主",
                        color=discord.Color.from_rgb(241, 196, 15), # 金黃色
                        reason="金主排行榜初始化"
                    )
                    role_created = True
                except discord.Forbidden:
                    return await interaction.followup.send("❌ 權限不足，無法建立金主身分組！", ephemeral=True)
            
            # 2. 建立唯讀文字頻道
            channel = discord.utils.get(guild.text_channels, name="💴｜金主排行榜")
            channel_created = False
            if not channel:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
                    guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, read_message_history=True)
                }
                try:
                    channel = await guild.create_text_channel(
                        name="💴｜金主排行榜",
                        overwrites=overwrites,
                        reason="金主排行榜初始化"
                    )
                    channel_created = True
                except discord.Forbidden:
                    return await interaction.followup.send("❌ 權限不足，無法建立金主排行榜頻道！", ephemeral=True)
            
            # 3. 雙向同步身分組成員
            await self.sync_sponsors_and_roles(guild)
            
            # 4. 先儲存基本設定 (避免 update 抓不到)
            settings = await self.db.get_sponsor_settings(guild_id)
            message_id = settings.get('message_id') if settings else None
            await self.db.set_sponsor_settings(guild_id, channel.id, message_id)
            
            # 5. 更新排行榜
            await self.update_leaderboard_message(guild)
            
            # 6. 回應訊息
            status_text = []
            if role_created: status_text.append("✅ 成功建立 `【💵】金主` 身分組")
            else: status_text.append("ℹ️ 已有 `【💵】金主` 身分組")
            
            if channel_created: status_text.append("✅ 成功建立 `💴｜金主排行榜` 唯讀頻道")
            else: status_text.append("ℹ️ 已有 `💴｜金主排行榜` 頻道")
            
            status_text.append("✅ 已同步金主身分組與資料庫名單，並刷新排行榜 Embed。")
            
            await interaction.followup.send(
                embed=EmbedFactory.success("金主排行榜初始化成功", "\n".join(status_text)),
                ephemeral=True
            )
        
        elif action == "add":
            if not member:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "請指定要新增的 `member`！"),
                    ephemeral=True
                )
                
            await interaction.response.defer(ephemeral=True)
            
            # 1. 賦予金主身分組
            role = discord.utils.get(guild.roles, name="【💵】金主")
            if not role:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("未初始化", "請先執行 `/sponsor action:初始化設定`！"),
                    ephemeral=True
                )
                
            try:
                await member.add_roles(role, reason="手動新增至金主排行榜")
            except discord.Forbidden:
                return await interaction.followup.send("❌ 權限不足，無法為該成員發送金主身分組！", ephemeral=True)
            
            # 2. 寫入資料庫
            thank_note = note if note else "感謝大力支持！💖"
            await self.db.add_sponsor(guild_id, member.id, thank_note)
            
            # 3. 刷新排行榜
            await self.update_leaderboard_message(guild)
            
            await interaction.followup.send(
                embed=EmbedFactory.success("新增成功", f"已成功將 {member.mention} 加入金主排行榜，並發送身分組！"),
                ephemeral=True
            )
        
        elif action == "remove":
            if not member:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "請指定要移除的 `member`！"),
                    ephemeral=True
                )
                
            await interaction.response.defer(ephemeral=True)
            
            # 1. 移除身分組
            role = discord.utils.get(guild.roles, name="【💵】金主")
            if role:
                try:
                    await member.remove_roles(role, reason="手動從金主排行榜中移除")
                except discord.Forbidden:
                    pass
            
            # 2. 從資料庫中刪除
            success = await self.db.remove_sponsor(guild_id, member.id)
            if not success:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("移除失敗", "該成員不在資料庫金主排行榜中。"),
                    ephemeral=True
                )
                
            # 3. 重新排序剩餘名單並刷新
            sponsors = await self.db.get_sponsors(guild_id)
            uids = [s['user_id'] for s in sponsors]
            await self.db.update_sponsor_positions(guild_id, uids)
            await self.update_leaderboard_message(guild)
            
            await interaction.followup.send(
                embed=EmbedFactory.success("移除成功", f"已成功將 {member.mention} 從金主排行榜中移除並收回身分組。"),
                ephemeral=True
            )
        
        elif action == "move":
            if not member or position is None:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "調整順序時必須指定 `member` 與目標 `position`！"),
                    ephemeral=True
                )
                
            if position <= 0:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("無效順序", "目標順序必須為大於 0 的整數！"),
                    ephemeral=True
                )
                
            await interaction.response.defer(ephemeral=True)
            
            sponsors = await self.db.get_sponsors(guild_id)
            uids = [s['user_id'] for s in sponsors]
            
            if member.id not in uids:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("操作失敗", f"{member.mention} 目前不在金主排行榜中！"),
                    ephemeral=True
                )
                
            # 調整順序
            uids.remove(member.id)
            target_idx = max(0, min(position - 1, len(uids)))
            uids.insert(target_idx, member.id)
            
            # 更新寫入並刷新
            await self.db.update_sponsor_positions(guild_id, uids)
            await self.update_leaderboard_message(guild)
            
            await interaction.followup.send(
                embed=EmbedFactory.success("調整順序成功", f"已成功將 {member.mention} 移動至排行榜第 `{target_idx + 1}` 位！"),
                ephemeral=True
            )
        
        elif action == "edit":
            if not member or not note:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("參數缺失", "編輯留言時必須指定 `member` 與新留言內容 `note`！"),
                    ephemeral=True
                )
                
            await interaction.response.defer(ephemeral=True)
            
            success = await self.db.update_sponsor_note(guild_id, member.id, note)
            if not success:
                return await interaction.followup.send(
                    embed=EmbedFactory.error("編輯失敗", f"該成員目前不在金主排行榜中。"),
                    ephemeral=True
                )
                
            await self.update_leaderboard_message(guild)
            await interaction.followup.send(
                embed=EmbedFactory.success("編輯留言成功", f"已成功變更 {member.mention} 的金主留言為：\n↳ ✧ *{note}* ✧"),
                ephemeral=True
            )
        
        elif action == "update":
            await interaction.response.defer(ephemeral=True)
            await self.sync_sponsors_and_roles(guild)
            success = await self.update_leaderboard_message(guild)
            if success:
                await interaction.followup.send(
                    embed=EmbedFactory.success("重新整理完畢", "已成功同步金主資料庫並刷新排行榜 Embed！"),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    embed=EmbedFactory.error("整理失敗", "請確認您是否已經執行過 `/sponsor action:初始化設定`？"),
                    ephemeral=True
                )

    @app_commands.command(name="promo", description="新增或移除全域輪替宣傳狀態（僅限擁有者使用）")
    @app_commands.describe(text="要放置在機器人狀態輪替中的宣傳文字", days="宣傳狀態持續的天數 (0 或負數代表移除該宣傳)")
    async def promo_command(self, interaction: discord.Interaction, text: str, days: int):
        # 僅限擁有者 ID
        if interaction.user.id != 1437408048934027274:
            return await interaction.response.send_message("❌ 你沒有權限執行此指令！", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        import time
        if days <= 0:
            # 移除指定宣傳文字
            original_len = len(self.bot.promo_statuses)
            self.bot.promo_statuses = [p for p in self.bot.promo_statuses if p["text"] != text]
            
            if len(self.bot.promo_statuses) < original_len:
                self.bot.save_promo_statuses()
                # 觸發狀態更新以更新列表
                self.bot.status_event.set()
                await interaction.followup.send(f"✅ 已將宣傳狀態 `{text}` 從輪替清單中移除。", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ 找不到內容為 `{text}` 的宣傳狀態。", ephemeral=True)
        else:
            # 新增或更新宣傳狀態
            expires_at = time.time() + (days * 86400)
            
            # 檢查是否已存在相同的文字，若存在則更新過期時間，否則新增
            found = False
            for p in self.bot.promo_statuses:
                if p["text"] == text:
                    p["expires_at"] = expires_at
                    found = True
                    break
            
            if not found:
                self.bot.promo_statuses.append({"text": text, "expires_at": expires_at})
                
            self.bot.save_promo_statuses()
            
            # 設定即時覆蓋，讓它立刻切換並在背景等待 30 秒
            self.bot.next_status_override = text
            self.bot.status_event.set()
            
            from datetime import datetime, timedelta
            expire_date = datetime.now() + timedelta(days=days)
            expire_str = expire_date.strftime("%Y-%m-%d %H:%M:%S")
            
            await interaction.followup.send(
                f"✅ **已成功將宣傳狀態加入全域輪替清單**！\n"
                f"📝 **宣傳內容**：`{text}`\n"
                f"⏱️ **持續時間**：`{days}` 天 (預計於 `{expire_str}` 到期後自動從輪替移除)\n"
                f"⚡ *機器人狀態已立即切換為此宣傳，並會在每個循環中與一般的狀態一起輪流切換！*",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SponsorSystem(bot))
