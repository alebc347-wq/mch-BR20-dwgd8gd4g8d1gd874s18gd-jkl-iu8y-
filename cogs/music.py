"""
音樂系統 Cog (Wavelink v3 版)
使用外部公共 Lavalink v4 伺服器進行音訊串流，0% 本地 CPU 佔用
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import random
from typing import Optional
import wavelink
import socket
import urllib.request
import ssl
from urllib.parse import urlparse

from config import Colors, Emoji, BadgeImages, LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD
from utils.embeds import EmbedFactory, PaginatorView

def is_node_online(uri: str, timeout: float = 1.5) -> bool:
    """快速測試 Lavalink 節點是否在線上，避免無效連線洗版"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(uri, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
            return True
    except urllib.error.HTTPError as e:
        # Lavalink 預設無驗證資訊時會回傳 401 Unauthorized，這代表節點在線且運作中
        if e.code in (401, 403, 302, 200):
            return True
        return False
    except Exception:
        return False

DEFAULT_247_URL = "https://www.youtube.com/watch?v=jfKfPfyJRdk"


class LoopMode:
    NONE = wavelink.QueueMode.normal
    LOOP_ONE = wavelink.QueueMode.loop
    LOOP_ALL = wavelink.QueueMode.loop_all


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI 元件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MusicPlayerView(discord.ui.View):
    """音樂播放控制按鈕 (保留供 /nowplaying 使用)"""

    def __init__(self, cog: "Music", owner_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ 只有使用指令的人才能操控此面板！", ephemeral=True)
            return False
        return True

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="music_prev")
    async def prev_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        """重新播放當前曲目"""
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.playing and player.current:
            try:
                await player.play(player.current)
                await interaction.response.send_message("⏮️ 重新播放當前曲目", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ 重新播放失敗：{e}", ephemeral=True)
        else:
            await interaction.response.send_message("目前沒有在播放音樂", ephemeral=True)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music_pause")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        """暫停/繼續"""
        player: wavelink.Player = interaction.guild.voice_client
        if player:
            await player.pause(not player.paused)
            status = "⏸️ 已暫停" if player.paused else "▶️ 繼續播放"
            await interaction.response.send_message(status, ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)
        else:
            await interaction.response.send_message("目前沒有在播放音樂", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        """跳過"""
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.playing:
            await player.skip()
            await interaction.response.send_message("⏭️ 已跳過", ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)
        else:
            await interaction.response.send_message("目前沒有在播放音樂", ephemeral=True)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="music_shuffle")
    async def shuffle_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """隨機排列"""
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.queue:
            player.queue.shuffle()
            await interaction.response.send_message("🔀 已隨機排列佇列", ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)
        else:
            await interaction.response.send_message("佇列為空", ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_music(self, interaction: discord.Interaction, button: discord.ui.Button):
        """停止"""
        player: wavelink.Player = interaction.guild.voice_client
        if player:
            await player.disconnect()
            await interaction.response.send_message("⏹️ 已停止播放並離開語音頻道", ephemeral=True)
        else:
            await interaction.response.send_message("目前沒有在播放音樂", ephemeral=True)


class SearchSelectMenu(discord.ui.Select):
    """搜尋結果選曲 Select Menu"""

    def __init__(self, tracks: list[wavelink.Playable], requester: discord.Member):
        self.track_list = tracks
        self.requester = requester

        options = []
        for i, track in enumerate(tracks[:5]):
            duration = Music._fmt_duration(track.length)
            label = track.title[:100] if track.title else f"Track {i+1}"
            desc = f"{track.author} • {duration}" if track.author else duration
            options.append(discord.SelectOption(
                label=label,
                description=desc[:100],
                value=str(i),
            ))

        super().__init__(placeholder="選擇要播放的歌曲...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog: "Music" = interaction.client.cogs.get("Music")
        if not cog:
            return await interaction.followup.send("❌ 音樂系統不可用", ephemeral=True)

        idx = int(self.values[0])
        track = self.track_list[idx]

        # 時長防禦限制
        player = await cog._ensure_voice(interaction)
        if not player:
            return

        is_247 = getattr(player, "mode_247", False)
        is_ultra = await cog.bot.db.is_guild_ultra(interaction.guild_id)
        is_pro = await cog.bot.db.is_guild_pro(interaction.guild_id)
        if is_247 or is_ultra:
            max_duration = 24 * 60 * 60 * 1000
        else:
            max_duration = 30 * 60 * 1000 if is_pro else 15 * 60 * 1000

        if track.length > max_duration:
            if is_247 or is_ultra:
                limit_text = "24 小時"
            else:
                limit_text = "30 分鐘 (Pro)" if is_pro else "15 分鐘"
            return await interaction.followup.send(
                embed=EmbedFactory.error("時長超出限制", f"此歌曲長度為 `{Music._fmt_duration(track.length)}`，超出 {limit_text} 限制。"),
                ephemeral=True
            )

        track.extras = {"requester_id": self.requester.id}

        await player.queue.put_wait(track)
        if not player.playing:
            next_t = player.queue.get()
            await player.play(next_t)

        await interaction.edit_original_response(
            embed=EmbedFactory.success("已加入佇列", f"**{track.title}** — {track.author}"),
            view=None,
        )

        # 刪除舊的面板
        old_msg = cog.controllers.get(interaction.guild.id)
        if old_msg:
            try:
                await old_msg.delete()
            except:
                pass
        
        old_view = cog.controller_views.get(interaction.guild.id)
        if old_view:
            old_view.stop()

        cog.controller_owners[interaction.guild.id] = interaction.user.id
        embed = await cog.get_controller_embed(interaction.guild)
        view = MusicControlView(cog, interaction.guild, owner_id=interaction.user.id)
        msg = await interaction.channel.send(embed=embed, view=view)
        cog.controllers[interaction.guild.id] = msg
        cog.controller_views[interaction.guild.id] = view


class SearchMoreButton(discord.ui.Button):
    """「顯示更多結果」按鈕"""

    def __init__(self):
        super().__init__(
            label="顯示更多結果",
            emoji="📋",
            style=discord.ButtonStyle.secondary,
            custom_id="search:more"
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user.id != view.requester.id:
            return await interaction.response.send_message("❌ 只有發起搜尋的人可以使用此按鈕。", ephemeral=True)

        # 增加顯示筆數，最大限制為 25
        view.limit = min(25, len(view.tracks))
        view.clear_items()
        
        # 重新添加擴展後的下拉選單
        view.add_item(SearchSelectMenu(view.tracks[:view.limit], view.requester))
        
        # 重新添加「重新搜尋」按鈕
        view.add_item(SearchRetryButton())
        
        # 更新原訊息內容
        embed = interaction.message.embeds[0]
        embed.description = f"已顯示前 {view.limit} 筆搜尋結果，請選擇要播放的歌曲："
        await interaction.response.edit_message(embed=embed, view=view)


class SearchRetryButton(discord.ui.Button):
    """「重新搜尋」按鈕"""

    def __init__(self):
        super().__init__(
            label="重新搜尋",
            emoji="🔍",
            style=discord.ButtonStyle.primary,
            custom_id="search:retry"
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user.id != view.requester.id:
            return await interaction.response.send_message("❌ 只有發起搜尋的人可以使用此按鈕。", ephemeral=True)

        cog = interaction.client.cogs.get("Music")
        if not cog:
            return await interaction.response.send_message("❌ 音樂系統目前不可用。", ephemeral=True)

        await interaction.response.send_modal(SearchRetryModal(cog))


class SearchRetryModal(discord.ui.Modal, title="重新搜尋音樂"):
    query = discord.ui.TextInput(
        label="輸入歌曲名稱或關鍵字",
        placeholder="例如：周杰倫 晴天...",
        style=discord.TextStyle.short,
        required=True,
        max_length=200
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = await self.cog._ensure_voice(interaction)
        if not player:
            return

        query_val = self.query.value
        try:
            tracks = await self.cog._search_with_failover(query_val)
        except Exception as e:
            return await self.cog._respond(
                interaction,
                embed=EmbedFactory.error("搜尋失敗", f"無法搜尋音樂：{e}"),
                ephemeral=True
            )

        if not tracks:
            return await self.cog._respond(
                interaction,
                embed=EmbedFactory.error("找不到結果", "找不到任何匹配的歌曲。"),
                ephemeral=True
            )

        # 播放清單處理
        if isinstance(tracks, wavelink.Playlist):
            is_247 = player and getattr(player, "mode_247", False)
            is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
            max_duration = 24 * 60 * 60 * 1000 if is_247 else (30 * 60 * 1000 if is_pro else 15 * 60 * 1000)

            added_count = 0
            for track in tracks.tracks:
                if track.length <= max_duration:
                    track.extras = {"requester_id": interaction.user.id}
                    await player.queue.put_wait(track)
                    added_count += 1
            embed = EmbedFactory.success(
                "已加入播放清單",
                f"已將播放清單 **{tracks.name}** 中 {added_count} 首符合時長限制的歌曲加入佇列。"
            )
            await self.cog._respond(interaction, embed=embed, ephemeral=False)

            if not player.playing:
                next_t = player.queue.get()
                await player.play(next_t)
            await self.cog.update_controller_message(interaction.guild)
        else:
            if len(tracks) == 1:
                track = tracks[0]
                is_247 = player and getattr(player, "mode_247", False)
                is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
                max_duration = 24 * 60 * 60 * 1000 if is_247 else (30 * 60 * 1000 if is_pro else 15 * 60 * 1000)
                if track.length > max_duration:
                    return await self.cog._respond(
                        interaction,
                        embed=EmbedFactory.error("時長超出限制", "此歌曲長度超出限制。"),
                        ephemeral=True
                    )
                track.extras = {"requester_id": interaction.user.id}
                await player.queue.put_wait(track)
                embed = EmbedFactory.success(
                    "已加入佇列",
                    f"**{track.title}** — {track.author}"
                )
                await self.cog._respond(interaction, embed=embed, ephemeral=False)
                if not player.playing:
                    next_t = player.queue.get()
                    await player.play(next_t)
                await self.cog.update_controller_message(interaction.guild)
            else:
                embed = discord.Embed(
                    title=f"{Emoji.SEARCH} 搜尋結果",
                    description="選擇要播放的歌曲：",
                    color=Colors.MUSIC,
                )
                view = SearchView(tracks, interaction.user)
                await interaction.followup.send(embed=embed, view=view, ephemeral=False)


class SearchView(discord.ui.View):
    def __init__(self, tracks: list[wavelink.Playable], requester: discord.Member, limit: int = 5):
        super().__init__(timeout=60)
        self.tracks = tracks
        self.requester = requester
        self.limit = limit

        self.clear_items()
        # 加入目前限制長度的選單
        self.add_item(SearchSelectMenu(tracks[:self.limit], requester))
        
        # 如果候選歌曲很多且尚未展開，加入顯示更多按鈕
        if len(tracks) > self.limit and self.limit < 25:
            self.add_item(SearchMoreButton())

        # 加入重新搜尋按鈕
        self.add_item(SearchRetryButton())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Modals
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PlaySongModal(discord.ui.Modal, title="搜尋並播放歌曲"):
    query = discord.ui.TextInput(
        label="請輸入歌曲名稱或 YouTube 網址",
        placeholder="例如：周杰倫 告白氣球 或 YouTube 網址...",
        style=discord.TextStyle.long,
        required=True,
        max_length=200
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = await self.cog._ensure_voice(interaction)
        if not player:
            return

        query_val = self.query.value
        try:
            tracks = await self.cog._search_with_failover(query_val)
        except Exception as e:
            return await interaction.followup.send(
                embed=EmbedFactory.error("搜尋失敗", f"無法搜尋音樂：{e}"),
                ephemeral=True
            )

        if not tracks:
            return await interaction.followup.send(
                embed=EmbedFactory.error("找不到結果", "找不到任何匹配的歌曲。"),
                ephemeral=True
            )

        # 檢查時長
        is_247 = getattr(player, "mode_247", False)
        is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
        if is_247:
            max_duration = 24 * 60 * 60 * 1000
        else:
            max_duration = 30 * 60 * 1000 if is_pro else 15 * 60 * 1000

        if isinstance(tracks, wavelink.Playlist):
            added = 0
            for track in tracks.tracks:
                if track.length <= max_duration:
                    track.extras = {"requester_id": interaction.user.id}
                    await player.queue.put_wait(track)
                    added += 1
            embed = EmbedFactory.success("已加入播放清單", f"已將播放清單中 {added} 首符合時長限制的歌曲加入佇列。")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            track = tracks[0]
            if track.length > max_duration:
                if is_247:
                    limit_text = "24 小時"
                else:
                    limit_text = "30 分鐘 (Pro)" if is_pro else "15 分鐘"
                return await interaction.followup.send(
                    embed=EmbedFactory.error("時長超出限制", f"此歌曲長度為 `{Music._fmt_duration(track.length)}`，超出 {limit_text} 限制。"),
                    ephemeral=True
                )
            track.extras = {"requester_id": interaction.user.id}
            await player.queue.put_wait(track)
            embed = EmbedFactory.success(
                "已加入佇列",
                f"**{track.title}** — {track.author}\n時長：`{Music._fmt_duration(track.length)}`",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        if not player.playing:
            next_t = player.queue.get()
            await player.play(next_t)

        await self.cog.update_controller_message(interaction.guild)


class VolumeModal(discord.ui.Modal, title="調整播放音量"):
    level = discord.ui.TextInput(
        label="音量大小 (0-5000)",
        placeholder="請輸入音量數字 (非 Pro 限 100)",
        style=discord.TextStyle.short,
        required=True,
        max_length=4
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("Bot 不在語音頻道中", ephemeral=True)

        is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
        max_vol = 5000 if is_pro else 100

        try:
            val = int(self.level.value)
            if not (0 <= val <= max_vol):
                raise ValueError
        except ValueError:
            if not is_pro:
                return await interaction.response.send_message(
                    "❌ 免費版限制音量範圍為 0-100。升級 Pro 專業版可解鎖最高 5000 音量！", 
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    "❌ 請輸入有效的數字 (0-5000)", 
                    ephemeral=True
                )

        await player.set_volume(val)
        if val <= 100:
            bar_filled = max(0, min(10, int(val / 10)))
        else:
            bar_filled = max(0, min(10, int(val / 500)))
        bar = "▰" * bar_filled + "▱" * (10 - bar_filled)

        await interaction.response.send_message(
            embed=EmbedFactory.success("音量已調整", f"`{bar}` **{val}%**"),
            ephemeral=True
        )
        await self.cog.update_controller_message(interaction.guild)


class AddFavoriteModal(discord.ui.Modal, title="手動新增最愛歌曲"):
    query = discord.ui.TextInput(
        label="請輸入歌曲名稱或網址",
        placeholder="例如：周杰倫 告白氣球 或 YouTube 網址...",
        style=discord.TextStyle.long,
        required=True,
        max_length=200
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query_val = self.query.value
        try:
            tracks = await self.cog._search_with_failover(query_val)
        except Exception as e:
            return await interaction.followup.send(f"❌ 搜尋歌曲失敗：{e}", ephemeral=True)

        if not tracks:
            return await interaction.followup.send("❌ 找不到該歌曲。", ephemeral=True)

        track = tracks[0]
        success = await self.cog.bot.db.add_favorite_song(
            user_id=interaction.user.id,
            title=track.title,
            uri=track.uri,
            author=track.author or "未知",
            duration=track.length
        )
        if success:
            await interaction.followup.send(
                embed=EmbedFactory.success("新增成功", f"已將 **{track.title}** 加入您的最愛清單。"),
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ 該歌曲已存在於您的最愛清單中。", ephemeral=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Select Menus
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class FavoritePlaySelect(discord.ui.Select):
    def __init__(self, cog: "Music", favorites: list):
        options = []
        for fav in favorites[:25]:
            title = fav["title"][:100]
            author = fav["author"] or "未知"
            uri = fav["uri"]
            options.append(discord.SelectOption(
                label=title,
                description=f"{author[:50]}",
                value=uri
            ))
        super().__init__(placeholder="選擇要點播的最愛歌曲...", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = await self.cog._ensure_voice(interaction)
        if not player:
            return

        uri = self.values[0]
        try:
            tracks = await self.cog._search_with_failover(uri)
        except Exception as e:
            return await interaction.followup.send(f"❌ 載入失敗：{e}", ephemeral=True)

        if not tracks:
            return await interaction.followup.send("❌ 找不到該歌曲項目。", ephemeral=True)

        track = tracks[0]
        track.extras = {"requester_id": interaction.user.id}
        await player.queue.put_wait(track)

        if not player.playing:
            next_t = player.queue.get()
            await player.play(next_t)

        await interaction.followup.send(
            embed=EmbedFactory.success("已從最愛清單播放", f"**{track.title}** — {track.author}"),
            ephemeral=True
        )
        await self.cog.update_controller_message(interaction.guild)


class FavoriteDeleteSelect(discord.ui.Select):
    def __init__(self, cog: "Music", favorites: list):
        options = []
        for fav in favorites[:25]:
            options.append(discord.SelectOption(
                label=fav["title"][:100],
                description=f"點擊刪除 | {fav['author'] or '未知'}",
                value=str(fav["id"])
            ))
        super().__init__(placeholder="選擇要刪除的最愛歌曲...", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        fav_id = int(self.values[0])
        success = await self.cog.bot.db.remove_favorite_song(interaction.user.id, fav_id)
        if success:
            await interaction.followup.send(
                embed=EmbedFactory.success("刪除成功", "已將該歌曲從您的最愛清單中移除。"),
                ephemeral=True
            )
        else:
            await interaction.followup.send("❌ 刪除失敗或找不到該音樂項目。", ephemeral=True)


class MusicDropdown(discord.ui.Select):
    def __init__(self, cog: "Music"):
        options = [
            discord.SelectOption(label="⭐ 將當前曲目加入最愛", value="fav_add_current", description="將目前正在播放的歌曲加入我的最愛", emoji="⭐"),
            discord.SelectOption(label="⭐ 手動搜尋加入最愛", value="fav_add_custom", description="輸入名稱或網址加入我的最愛", emoji="📝"),
            discord.SelectOption(label="⭐ 從最愛清單點播歌曲", value="fav_play", description="瀏覽並點播最愛的音樂", emoji="🎵"),
            discord.SelectOption(label="⭐ 刪除最愛清單的歌曲", value="fav_delete", description="從我的最愛清單移除歌曲", emoji="🗑️"),
            discord.SelectOption(label="🔀 隨機排列佇列", value="shuffle", description="將佇列中的歌曲隨機排序", emoji="🔀"),
            discord.SelectOption(label="🔁 循環播放切換", value="loop_toggle", description="切換單曲、佇列循環或關閉", emoji="🔁"),
            discord.SelectOption(label="🔈 調整播放音量", value="volume", description="設定播放器的音量百分比", emoji="🔈"),
            discord.SelectOption(label="📌 開啟/關閉 24/7 模式", value="toggle_247", description="切換機器人是否 24 小時駐留語音", emoji="📌"),
            discord.SelectOption(label="🗑️ 清空播放佇列", value="clear_queue", description="清除所有排隊中的音樂", emoji="❌"),
        ]
        super().__init__(placeholder="更多音樂控制與最愛功能...", options=options, custom_id="mc_dropdown")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        player: wavelink.Player = interaction.guild.voice_client

        if val == "fav_add_current":
            if not player or not player.current:
                return await interaction.response.send_message("❌ 目前沒有正在播放的歌曲。", ephemeral=True)
            track = player.current
            success = await self.cog.bot.db.add_favorite_song(
                user_id=interaction.user.id,
                title=track.title,
                uri=track.uri,
                author=track.author or "未知",
                duration=track.length
            )
            if success:
                await interaction.response.send_message(
                    embed=EmbedFactory.success("已加到最愛", f"成功將 **{track.title}** 加入您的最愛清單！"),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ 該歌曲已存在於您的最愛清單中。", ephemeral=True)

        elif val == "fav_add_custom":
            await interaction.response.send_modal(AddFavoriteModal(self.cog))

        elif val == "fav_play":
            favorites = await self.cog.bot.db.get_favorite_songs(interaction.user.id)
            if not favorites:
                return await interaction.response.send_message("❌ 您的最愛清單還是空的！快去加入一些歌曲吧！", ephemeral=True)
            view = discord.ui.View(timeout=60)
            view.add_item(FavoritePlaySelect(self.cog, favorites))
            await interaction.response.send_message("請選擇要點播的最愛歌曲：", view=view, ephemeral=True)

        elif val == "fav_delete":
            favorites = await self.cog.bot.db.get_favorite_songs(interaction.user.id)
            if not favorites:
                return await interaction.response.send_message("❌ 您的最愛清單還是空的！", ephemeral=True)
            view = discord.ui.View(timeout=60)
            view.add_item(FavoriteDeleteSelect(self.cog, favorites))
            await interaction.response.send_message("請選擇要從最愛中刪除的歌曲：", view=view, ephemeral=True)

        elif val == "shuffle":
            if not player or not player.queue:
                return await interaction.response.send_message("❌ 目前播放佇列為空，無法隨機排列。", ephemeral=True)
            player.queue.shuffle()
            await interaction.response.send_message("🔀 已隨機打亂目前佇列！", ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)

        elif val == "loop_toggle":
            is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
            if not is_pro:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("功能限制", "❌ 循環播放功能為 Pro 專業版專屬功能！"),
                    ephemeral=True
                )
            if not player:
                return await interaction.response.send_message("❌ 機器人目前未連線至語音頻道。", ephemeral=True)
            
            if getattr(player, "mode_247", False):
                player.mode_247 = False
                player.queue.mode = wavelink.QueueMode.normal
                status = "🔁 已關閉 24/7 模式與循環"
            else:
                current_mode = player.queue.mode
                if current_mode == wavelink.QueueMode.normal:
                    player.queue.mode = wavelink.QueueMode.loop
                    status = "🔂 單曲循環已開啟"
                elif current_mode == wavelink.QueueMode.loop:
                    player.queue.mode = wavelink.QueueMode.loop_all
                    status = "🔁 佇列循環已開啟"
                else:
                    player.queue.mode = wavelink.QueueMode.normal
                    status = "循環模式已關閉"
            await interaction.response.send_message(embed=EmbedFactory.success(status), ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)

        elif val == "volume":
            await interaction.response.send_modal(VolumeModal(self.cog))

        elif val == "toggle_247":
            pro_cog = interaction.client.cogs.get("Pro")
            if pro_cog and not await pro_cog.check_pro(interaction):
                return
            if not player:
                player = await self.cog._ensure_voice(interaction)
                if not player:
                    return
            status = await self.cog.run_247_toggle(player, interaction.guild, interaction.user.id)
            await interaction.response.send_message(embed=EmbedFactory.success("24/7 模式", status), ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)

        elif val == "clear_queue":
            if not player:
                return await interaction.response.send_message("❌ 機器人目前未連線至語音頻道。", ephemeral=True)
            player.queue.clear()
            await interaction.response.send_message("🗑️ 已清空排隊佇列！", ephemeral=True)
            await self.cog.update_controller_message(interaction.guild)


class MusicControlView(discord.ui.View):
    def __init__(self, cog: "Music", guild: discord.Guild, owner_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild
        self.owner_id = owner_id or (cog.controller_owners.get(guild.id) if cog else None)

        player: wavelink.Player = guild.voice_client
        if player:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.custom_id == "mc_pause":
                        item.emoji = "▶️" if player.paused else "⏸️"
                        item.label = "繼續" if player.paused else "暫停"
                    elif item.custom_id == "mc_loop":
                        if getattr(player, "mode_247", False):
                            item.label = "循環: 24/7"
                        else:
                            loop_labels = {wavelink.QueueMode.normal: "關閉", wavelink.QueueMode.loop: "單曲", wavelink.QueueMode.loop_all: "佇列"}
                            item.label = f"循環: {loop_labels.get(player.queue.mode, '關閉')}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ 只有使用指令的人才能操控此面板！", ephemeral=True)
            return False
        return True

    # Row 1
    @discord.ui.button(emoji="👍", style=discord.ButtonStyle.secondary, custom_id="mc_like", row=0)
    async def like_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👍 感謝回饋！", ephemeral=True)

    @discord.ui.button(emoji="🤍", style=discord.ButtonStyle.secondary, custom_id="mc_heart", row=0)
    async def heart_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.current:
            track = player.current
            success = await self.cog.bot.db.add_favorite_song(
                user_id=interaction.user.id, title=track.title, uri=track.uri,
                author=track.author or "未知", duration=track.length
            )
            if success:
                await interaction.response.send_message(f"🤍 已將 **{track.title}** 加入最愛！", ephemeral=True)
            else:
                await interaction.response.send_message("❌ 該歌曲已經在您的最愛清單中了。", ephemeral=True)
        else:
            await interaction.response.send_message("❌ 目前沒有正在播放的歌曲。", ephemeral=True)

    @discord.ui.button(emoji="👎", style=discord.ButtonStyle.secondary, custom_id="mc_dislike", row=0)
    async def dislike_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("👎 感謝回饋！", ephemeral=True)

    # Row 2
    @discord.ui.button(label="音量", emoji="🔈", style=discord.ButtonStyle.secondary, custom_id="mc_volume", row=1)
    async def volume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VolumeModal(self.cog))

    @discord.ui.button(label="返回", emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="mc_prev", row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        player: wavelink.Player = interaction.guild.voice_client
        if player and player.playing and player.current:
            try:
                await player.play(player.current)
                await interaction.followup.send("⏮️ 已重新播放當前曲目", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ 重新播放失敗：{e}", ephemeral=True)
        else:
            await interaction.followup.send("❌ 目前沒有音樂。", ephemeral=True)

    @discord.ui.button(label="暫停", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="mc_pause", row=1)
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return
        await player.pause(not player.paused)
        await self.cog.update_controller_message(interaction.guild)

    @discord.ui.button(label="跳過", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="mc_skip", row=1)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return
        await player.skip()
        await self.cog.update_controller_message(interaction.guild)

    # Row 3
    @discord.ui.button(label="停止", emoji="🚫", style=discord.ButtonStyle.secondary, custom_id="mc_stop", row=2)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return
        await player.disconnect()

    # Row 4
    @discord.ui.button(label="佇列", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="mc_queue", row=3)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message("❌ 機器人未連線。", ephemeral=True)
        if not player.queue and not player.current:
            return await interaction.response.send_message("📋 佇列目前為空。", ephemeral=True)
        tracks_per_page = 10
        queue_list = list(player.queue)
        pages = []
        total_pages = max(1, (len(queue_list) + tracks_per_page - 1) // tracks_per_page)
        for page_num in range(total_pages):
            start = page_num * tracks_per_page
            page_tracks = queue_list[start:start + tracks_per_page]
            track_infos = [f"**{t.title}** — `{Music._fmt_duration(t.length)}`" for t in page_tracks]
            now_playing = player.current.title if player.current else ""
            pages.append(EmbedFactory.queue_page(track_infos, page_num + 1, total_pages, now_playing))
        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0], ephemeral=True)
        else:
            await interaction.response.send_message(embed=pages[0], view=PaginatorView(pages, interaction.user.id), ephemeral=True)

    @discord.ui.button(label="循環: 關閉", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="mc_loop", row=3)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_pro = await self.cog.bot.db.is_guild_pro(interaction.guild_id)
        if not is_pro:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("功能限制", "❌ 循環播放功能為 Pro 專業版專屬功能！"),
                ephemeral=True
            )
        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return
            
        if getattr(player, "mode_247", False):
            player.mode_247 = False
            player.queue.mode = wavelink.QueueMode.normal
        else:
            current_mode = player.queue.mode
            if current_mode == wavelink.QueueMode.normal:
                player.queue.mode = wavelink.QueueMode.loop
            elif current_mode == wavelink.QueueMode.loop:
                player.queue.mode = wavelink.QueueMode.loop_all
            else:
                player.queue.mode = wavelink.QueueMode.normal
                
        await self.cog.update_controller_message(interaction.guild)

    # Row 5
    @discord.ui.button(label="自動播放: 關閉", emoji="🎵", style=discord.ButtonStyle.secondary, custom_id="mc_autoplay", row=4)
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ 自動播放功能尚在開發中！", ephemeral=True)

    @discord.ui.button(label="歌詞", emoji="🔠", style=discord.ButtonStyle.secondary, custom_id="mc_lyrics", row=4)
    async def lyrics_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ 歌詞功能尚在開發中！", ephemeral=True)



class PlayMusicModal(discord.ui.Modal, title="點播歌曲"):
    query = discord.ui.TextInput(
        label="你要聽什麼歌？",
        placeholder="輸入歌曲名稱、關鍵字或 YouTube 連結...",
        required=True,
        max_length=200
    )

    def __init__(self, cog: "Music"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        # 先 defer，因為搜尋跟播放需要一些時間
        await interaction.response.defer()
        # 呼叫播放邏輯
        await self.cog.play_search(interaction, self.query.value)
        # 把原本的提示按鈕訊息修改，避免畫面殘留按鈕
        try:
            await interaction.edit_original_response(content="✅ 已開始搜尋並載入歌曲！", view=None)
        except Exception:
            pass


class PlayPromptView(discord.ui.View):
    def __init__(self, cog: "Music", author_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有想聽歌的人才能點擊此按鈕！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔍 輸入歌名/連結", style=discord.ButtonStyle.primary, custom_id="play_prompt_input")
    async def input_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PlayMusicModal(self.cog)
        await interaction.response.send_modal(modal)


class JoinVoiceCheckView(discord.ui.View):
    def __init__(self, cog: "Music", author_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有想聽歌的人才能點擊此按鈕！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="我加入好了", style=discord.ButtonStyle.success, custom_id="join_voice_done")
    async def joined_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("❌ 您還沒有加入任何語音頻道喔！請先加入後再點擊此按鈕。", ephemeral=True)

        await interaction.response.defer()
        player = await self.cog._ensure_voice(interaction)
        if not player:
            return

        view = PlayPromptView(self.cog, self.author_id)
        await interaction.edit_original_response(content="你要聽什麼", view=view)

    @discord.ui.button(label="算了", style=discord.ButtonStyle.danger, custom_id="join_voice_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="算了，那這次先不播歌囉！", view=self)
        self.stop()


class AskListenView(discord.ui.View):
    def __init__(self, cog: "Music", author_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有想聽歌的人才能點擊此按鈕！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="要", style=discord.ButtonStyle.primary, custom_id="ask_listen_yes")
    async def yes_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = JoinVoiceCheckView(self.cog, self.author_id)
        await interaction.response.edit_message(content="你先加入語音頻道", view=view)

    @discord.ui.button(label="否", style=discord.ButtonStyle.secondary, custom_id="ask_listen_no")
    async def no_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="算了，那下次想聽歌再找我吧！", view=self)
        self.stop()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主 Music Cog 類別
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Music(commands.Cog):
    """音樂系統 — Lavalink (Wavelink v3)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.controllers: dict[int, discord.Message] = {}  # guild_id -> 面板訊息
        self.controller_views: dict[int, discord.ui.View] = {}  # guild_id -> 面板 View 參照
        self.controller_owners: dict[int, int] = {}  # guild_id -> owner_id (使用指令的人)
        self._voice_connect_locks: dict[int, asyncio.Lock] = {}  # guild_id -> 連線鎖
        self.controller_updater.start()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if "聽歌" in message.content:
            view = AskListenView(self, message.author.id)
            await message.reply("好啊好啊你要聽歌的話", view=view)

    def cog_unload(self):
        self.controller_updater.cancel()

    @tasks.loop(seconds=5)
    async def controller_updater(self):
        """每 5 秒更新一次正在播放中的音樂控制面板進度條"""
        for player in self.bot.voice_clients:
            if isinstance(player, wavelink.Player) and player.playing and not player.paused:
                try:
                    await self.update_controller_message(player.guild)
                except Exception:
                    pass

    async def cog_load(self):
        """Cog 載入時，連接自訂與公共 Lavalink 節點池"""
        nodes = []
        
        # 1. 經社群驗證的高品質公共 Lavalink v4 節點池
        public_nodes = [
            wavelink.Node(
                identifier="TriniumHost-SSL",
                uri="https://lavalink-v4.triniumhost.com:443",
                password="free"
            ),
            wavelink.Node(
                identifier="Jirayu-SSL",
                uri="https://lavalink.jirayu.net:443",
                password="youshallnotpass"
            ),
            wavelink.Node(
                identifier="Serenetia-SSL",
                uri="https://lavalinkv4.serenetia.com:443",
                password="https://seretia.link/discord"
            )
        ]
        
        # 逐一檢查公共節點是否在線，避免無效節點引發連線報錯
        for node in public_nodes:
            if is_node_online(node.uri):
                nodes.append(node)
            else:
                print(f"⚠️ 公共節點 {node.identifier} [{node.uri}] 目前無法連線，已暫時忽略以避免連線失敗訊息洗版。")

        # 2. 如果有配置自訂節點，且不與上述公共節點重複，則加入節點池
        if LAVALINK_HOST:
            scheme = "https" if LAVALINK_PORT == 443 else "http"
            custom_uri = f"{scheme}://{LAVALINK_HOST}:{LAVALINK_PORT}"
            
            # 檢查是否已在公共節點池中，避免重複添加
            is_duplicate = any(node.uri.rstrip('/') == custom_uri.rstrip('/') for node in public_nodes)
            
            if not is_duplicate:
                if is_node_online(custom_uri):
                    nodes.append(
                        wavelink.Node(
                            identifier="Custom-Config-Node",
                            uri=custom_uri,
                            password=LAVALINK_PASSWORD
                        )
                    )
                    print(f"📡 已將設定檔的自訂節點 [{LAVALINK_HOST}:{LAVALINK_PORT}] 加入連線池。")
                else:
                    print(f"⚠️ 自訂節點 [{LAVALINK_HOST}:{LAVALINK_PORT}] 目前未啟動或無法連線，已暫時忽略以避免錯誤洗版。")
        
        try:
            await wavelink.Pool.connect(nodes=nodes, client=self.bot)
            print("✅ Wavelink 已成功連接 Lavalink 節點池！")
        except Exception as e:
            print(f"❌ Wavelink 連接節點池失敗: {e}")

    async def _search_with_failover(self, query: str) -> list[wavelink.Playable] | wavelink.Playlist | None:
        """
        在所有已連接的 Lavalink 節點中嘗試搜尋音樂，如果遇到 524 逾時或其他錯誤則自動切換至下一個節點。
        """
        connected_nodes = [
            node for node in wavelink.Pool.nodes.values()
            if node.status == wavelink.NodeStatus.CONNECTED
        ]
        
        if not connected_nodes:
            connected_nodes = list(wavelink.Pool.nodes.values())
            
        if not connected_nodes:
            raise RuntimeError("沒有可用的 Lavalink 節點。")

        # 隨機打亂以做簡單的負載平衡
        random.shuffle(connected_nodes)

        last_error = None
        for node in connected_nodes:
            try:
                tracks = await asyncio.wait_for(
                    wavelink.Playable.search(query, node=node),
                    timeout=8.0
                )
                if tracks:
                    print(f"🔍 節點 [{node.identifier}] 搜尋成功且有結果：'{query}'")
                    return tracks
                else:
                    print(f"⚠️ 節點 [{node.identifier}] 搜尋返回空結果，嘗試其他節點...")
            except Exception as e:
                last_error = e
                print(f"⚠️ 節點 [{node.identifier}] 搜尋發生錯誤：{e}")
                continue

        if last_error:
            raise last_error
        return None

    # ─── 工具方法 ─────────────────────────────────────────

    @staticmethod
    def _fmt_duration(ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        hours = minutes // 60
        minutes = minutes % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _format_duration(ms: int) -> str:
        return Music._fmt_duration(ms)

    async def _respond(self, interaction: discord.Interaction, embed: discord.Embed, ephemeral: bool = True):
        """安全地對 Interaction 進行回覆"""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
        except Exception:
            try:
                await interaction.channel.send(embed=embed)
            except Exception:
                pass

    async def _ensure_voice(self, interaction: discord.Interaction) -> wavelink.Player | None:
        """確保用戶在語音頻道並連接，回傳 wavelink.Player"""
        pro_cog = self.bot.cogs.get("Pro")
        if pro_cog and not await pro_cog.check_pro(interaction):
            return None

        if not interaction.user.voice or not interaction.user.voice.channel:
            await self._respond(
                interaction,
                embed=EmbedFactory.error("未加入語音頻道", "你需要先加入一個語音頻道！"),
                ephemeral=True,
            )
            return None

        guild_id = interaction.guild_id
        if guild_id not in self._voice_connect_locks:
            self._voice_connect_locks[guild_id] = asyncio.Lock()

        async with self._voice_connect_locks[guild_id]:
            target_channel = interaction.user.voice.channel
            player: wavelink.Player = interaction.guild.voice_client

            if player:
                if isinstance(player, wavelink.Player) and player.connected:
                    if player.channel != target_channel:
                        permissions = target_channel.permissions_for(interaction.guild.me)
                        if not permissions.connect:
                            await self._respond(
                                interaction,
                                embed=EmbedFactory.error(
                                    "權限不足", 
                                    f"我沒有權限連接到您的語音頻道 {target_channel.mention}，請確認頻道設定是否允許我連接！"
                                ),
                                ephemeral=True,
                            )
                            return None
                        if not permissions.speak:
                            await self._respond(
                                interaction,
                                embed=EmbedFactory.error(
                                    "權限不足", 
                                    f"我沒有權限在語音頻道 {target_channel.mention} 中發言/播放，請開啟發言權限！"
                                ),
                                ephemeral=True,
                            )
                            return None
                        try:
                            await player.move_to(target_channel)
                        except Exception as ex:
                            print(f"[Music] 移動至頻道 {target_channel.name} 出錯: {ex}")
                    return player
                else:
                    # 若語音連線已斷開或不是 wavelink.Player，先強制清除，避免狀態衝突
                    try:
                        await player.disconnect(force=True)
                    except Exception as ex:
                        print(f"[Music] 斷開不完整或不相容連線時出錯: {ex}")
                    await asyncio.sleep(0.5)

            # 若 Discord Gateway 殘留舊的語音狀態，強制發送 channel=None 進行清除
            if interaction.guild.me and interaction.guild.me.voice:
                try:
                    await interaction.guild.change_voice_state(channel=None)
                    await asyncio.sleep(0.5)
                except Exception as ex:
                    print(f"[Music] 清理 Gateway 殘留語音狀態時出錯: {ex}")

            # 再次檢查用戶是否在語音頻道 (以防在前面 disconnect 耗時過程中用戶離開了)
            if not interaction.user.voice or not interaction.user.voice.channel:
                await self._respond(
                    interaction,
                    embed=EmbedFactory.error("未加入語音頻道", "連線前偵測到您已離開語音頻道！"),
                    ephemeral=True,
                )
                return None

            voice_channel = interaction.user.voice.channel

            # 檢查連接與發言權限，避免超時錯誤
            permissions = voice_channel.permissions_for(interaction.guild.me)
            if not permissions.connect:
                await self._respond(
                    interaction,
                    embed=EmbedFactory.error(
                        "權限不足", 
                        f"我沒有權限連接到您的語音頻道 {voice_channel.mention}，請確認頻道設定是否允許我連接！"
                    ),
                    ephemeral=True,
                )
                return None
            if not permissions.speak:
                await self._respond(
                    interaction,
                    embed=EmbedFactory.error(
                        "權限不足", 
                        f"我沒有權限在語音頻道 {voice_channel.mention} 中發言/播放，請開啟發言權限！"
                    ),
                    ephemeral=True,
                )
                return None

            # 檢查頻道是否人數已滿
            if voice_channel.user_limit > 0 and len(voice_channel.members) >= voice_channel.user_limit:
                if not (permissions.administrator or permissions.move_members):
                    await self._respond(
                        interaction,
                        embed=EmbedFactory.error(
                            "頻道人數已滿", 
                            f"語音頻道 {voice_channel.mention} 人數已滿，且我沒有權限（移動成員）強行進入！"
                        ),
                        ephemeral=True,
                    )
                    return None

            # 嘗試連線，若發生異常或逾時則重置 Gateway 狀態並重試
            try:
                player = await voice_channel.connect(cls=wavelink.Player, timeout=20.0, self_deaf=True)
                if not hasattr(player, "mode_247"):
                    player.mode_247 = False
                return player
            except Exception as e:
                # 重試前檢查用戶是否在語音頻道
                if not interaction.user.voice or not interaction.user.voice.channel:
                    await self._respond(
                        interaction,
                        embed=EmbedFactory.error("未加入語音頻道", "連線逾時重試時，偵測到您已離開語音頻道。"),
                        ephemeral=True,
                    )
                    return None
                voice_channel = interaction.user.voice.channel
                print(f"⚠️ 連線至語音頻道 {voice_channel.name} 失敗/逾時，嘗試強制重置連線狀態後重試：{e}")
                try:
                    for vc in self.bot.voice_clients:
                        if vc.guild.id == interaction.guild.id:
                            await vc.disconnect(force=True)
                except Exception as ex:
                    print(f"[Music] 重試前的強制斷線出錯: {ex}")

                try:
                    if interaction.guild.me and interaction.guild.me.voice:
                        await interaction.guild.change_voice_state(channel=None)
                except Exception as ex:
                    print(f"[Music] 重試前清理 Gateway 語音狀態出錯: {ex}")
                
                await asyncio.sleep(1.5)
                
                # 重試前檢查用戶是否在語音頻道
                if not interaction.user.voice or not interaction.user.voice.channel:
                    await self._respond(
                        interaction,
                        embed=EmbedFactory.error("未加入語音頻道", "重試連線前，偵測到您已離開語音頻道。"),
                        ephemeral=True,
                    )
                    return None
                
                voice_channel = interaction.user.voice.channel
                # 第二次嘗試連線
                try:
                    player = await voice_channel.connect(cls=wavelink.Player, timeout=20.0, self_deaf=True)
                    if not hasattr(player, "mode_247"):
                        player.mode_247 = False
                    print(f"✅ 重試後成功連線至語音頻道 {voice_channel.name}")
                    return player
                except Exception as retry_err:
                    await self._respond(
                        interaction,
                        embed=EmbedFactory.error(
                            "語音連線失敗 (重試後)",
                            f"重試後仍無法連線至語音頻道。\n\n**詳細錯誤：**\n`{type(retry_err).__name__}: {retry_err}`"
                        ),
                        ephemeral=True,
                    )
                    return None

    async def run_247_toggle(self, player: wavelink.Player, guild: discord.Guild, user_id: int) -> str:
        player.mode_247 = not player.mode_247

        if player.mode_247:
            status = "🟢 已開啟 24/7 模式，機器人將不會自動退出頻道。"
            player.queue.mode = wavelink.QueueMode.loop_all
            if not player.playing:
                try:
                    tracks = await self._search_with_failover(DEFAULT_247_URL)
                    if tracks:
                        track = tracks[0]
                        track.extras = {"requester_id": user_id}
                        await player.queue.put_wait(track)
                        next_t = player.queue.get()
                        await player.play(next_t)
                        status += "\n🎵 已自動為您播放 24 小時無間斷音樂！"
                except Exception as e:
                    status += f"\n⚠️ 自動播放時發生錯誤：{e}"
        else:
            status = "🔴 已關閉 24/7 模式，閒置時將會自動退出。"
            if player.queue.mode == wavelink.QueueMode.loop_all:
                player.queue.mode = wavelink.QueueMode.normal

        return status

    # ─── 控制面板 ─────────────────────────────────────────

    async def get_controller_embed(self, guild: discord.Guild) -> discord.Embed:
        player: wavelink.Player = guild.voice_client
        
        if not player or not player.connected or not player.current:
            embed = discord.Embed(
                title="🎵 音樂播放控制中心", 
                description="📭 **目前沒有正在播放的音樂。**\n請使用 `/play` 點歌。",
                color=0x2B2D31
            )
            return embed

        track = player.current
        requester_id = getattr(track.extras, "requester_id", None) if track.extras else None
        member = guild.get_member(requester_id) if requester_id else None
        requester_name = f"@{member.display_name}" if member else "@未知"
        
        # 動態進度條計算
        position_ms = int(player.position) if hasattr(player, "position") else 0
        pos_str = self._format_duration(position_ms)
        dur_str = self._format_duration(track.length)
        
        pct = position_ms / track.length if track.length > 0 else 0
        bar_length = 20
        filled = int(pct * bar_length)
        filled = max(0, min(bar_length, filled))
        bar = "▬" * filled + "🔘" + "▬" * (bar_length - filled)
        
        progress_bar = f"`{pos_str}` {bar} `{dur_str}`"
        
        embed = discord.Embed(
            title=f"正在播放 — 請求者: {requester_name}", 
            description=(
                f"` {track.author} `\n"
                f"**[{track.title}]({track.uri})**\n\n"
                f"{progress_bar}"
            ),
            color=0x2B2D31
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    async def update_controller_message(self, guild: discord.Guild):
        msg = self.controllers.get(guild.id)
        if not msg:
            return
        try:
            embed = await self.get_controller_embed(guild)
            owner_id = self.controller_owners.get(guild.id)
            view = MusicControlView(self, guild, owner_id=owner_id)
            old_view = self.controller_views.get(guild.id)
            if old_view:
                old_view.stop()
            self.controller_views[guild.id] = view
            await msg.edit(embed=embed, view=view)
        except Exception:
            self.controllers.pop(guild.id, None)
            self.controller_views.pop(guild.id, None)

    # ─── 斜線指令 ─────────────────────────────────────────

    @app_commands.command(name="music_menu", description="召喚音樂系統 UI 控制面板")
    async def music_menu(self, interaction: discord.Interaction):
        pro_cog = self.bot.cogs.get("Pro")
        if pro_cog and not await pro_cog.check_pro(interaction):
            return

        await interaction.response.defer()
        old_msg = self.controllers.get(interaction.guild.id)
        if old_msg:
            try:
                await old_msg.delete()
            except Exception:
                pass

        old_view = self.controller_views.get(interaction.guild.id)
        if old_view:
            old_view.stop()

        self.controller_owners[interaction.guild.id] = interaction.user.id
        embed = await self.get_controller_embed(interaction.guild)
        view = MusicControlView(self, interaction.guild, owner_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, view=view)
        self.controllers[interaction.guild.id] = msg
        self.controller_views[interaction.guild.id] = view

    @app_commands.command(name="247", description="切換 24/7 無間斷播放模式")
    async def toggle_247(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pro_cog = self.bot.cogs.get("Pro")
        if pro_cog and not await pro_cog.check_pro(interaction):
            return
        player = await self._ensure_voice(interaction)
        if not player:
            return
        status = await self.run_247_toggle(player, interaction.guild, interaction.user.id)
        await interaction.followup.send(embed=EmbedFactory.success("24/7 模式", status))
        await self.update_controller_message(interaction.guild)

    async def play_search(self, interaction: discord.Interaction, query: str):
        # 如果是 YouTube 的 watch+list 連結，或是 youtu.be 的 list 連結，自動轉換為純 playlist 連結以載入整張歌單
        if "youtube.com" in query or "youtu.be" in query:
            import urllib.parse as urlparse
            try:
                parsed = urlparse.urlparse(query)
                params = urlparse.parse_qs(parsed.query)
                if "list" in params:
                    playlist_id = params["list"][0]
                    query = f"https://www.youtube.com/playlist?list={playlist_id}"
            except Exception as e:
                print(f"[Music] 嘗試解析/轉換播放清單網址時出錯: {e}")

        player = await self._ensure_voice(interaction)
        if not player:
            return

        try:
            tracks = await self._search_with_failover(query)
        except Exception as e:
            return await interaction.followup.send(
                embed=EmbedFactory.error("搜尋失敗", f"無法搜尋音樂：{e}")
            )

        if not tracks:
            return await interaction.followup.send(
                embed=EmbedFactory.error("找不到結果", "找不到任何匹配的歌曲。")
            )

        is_247 = player and getattr(player, "mode_247", False)
        is_ultra = await self.bot.db.is_guild_ultra(interaction.guild_id)
        is_pro = await self.bot.db.is_guild_pro(interaction.guild_id)
        if is_247 or is_ultra:
            max_duration = 24 * 60 * 60 * 1000
        else:
            max_duration = 30 * 60 * 1000 if is_pro else 15 * 60 * 1000

        # 如果是播放清單
        if isinstance(tracks, wavelink.Playlist):
            playlist = tracks
            added_count = 0
            for track in playlist.tracks:
                if track.length <= max_duration:
                    track.extras = {"requester_id": interaction.user.id}
                    await player.queue.put_wait(track)
                    added_count += 1
            embed = EmbedFactory.success(
                "已加入播放清單",
                f"已將播放清單 **{playlist.name}** 中 {added_count} 首符合時長限制的歌曲加入佇列。"
            )
            await interaction.followup.send(embed=embed)
        else:
            # 搜尋字詞且不是 URL 時 → 顯示選單讓用戶選
            if not query.startswith(("http://", "https://")) and len(tracks) > 1:
                embed = discord.Embed(
                    title=f"{Emoji.SEARCH} 搜尋結果",
                    description="選擇要播放的歌曲：",
                    color=Colors.MUSIC,
                )
                view = SearchView(tracks, interaction.user)
                return await interaction.followup.send(embed=embed, view=view)

            # 單首 URL
            track = tracks[0]
            if track.length > max_duration:
                if is_247 or is_ultra:
                    return await interaction.followup.send(
                        embed=EmbedFactory.error(
                            "時長超出限制",
                            f"⚠️ 此歌曲長度為 `{self._format_duration(track.length)}`，超出 24 小時限制。"
                        )
                    )
                else:
                    limit_min = 30 if is_pro else 15
                    return await interaction.followup.send(
                        embed=EmbedFactory.error(
                            "時長超出限制",
                            f"⚠️ 為了防止主機 CPU 暴衝與卡死，本機器人限制播放 {limit_min} 分鐘以內的歌曲。\n"
                            f"這首歌長度為 `{self._format_duration(track.length)}`。\n\n"
                            f"💡 *提示：升級 Ultra 旗艦版可解鎖 24 小時超長歌曲播放！*"
                        )
                    )
            track.extras = {"requester_id": interaction.user.id}
            await player.queue.put_wait(track)
            embed = EmbedFactory.success(
                "已加入佇列",
                f"**{track.title}** — {track.author}\n時長：`{self._format_duration(track.length)}`"
            )
            await interaction.followup.send(embed=embed)

        if not player.playing:
            next_t = player.queue.get()
            await player.play(next_t)

        # 刪除舊的面板
        old_msg = self.controllers.get(interaction.guild.id)
        if old_msg:
            try:
                await old_msg.delete()
            except:
                pass
        
        old_view = self.controller_views.get(interaction.guild.id)
        if old_view:
            old_view.stop()
            
        self.controller_owners[interaction.guild.id] = interaction.user.id
        embed = await self.get_controller_embed(interaction.guild)
        view = MusicControlView(self, interaction.guild, owner_id=interaction.user.id)
        msg = await interaction.followup.send(embed=embed, view=view)
        self.controllers[interaction.guild.id] = msg
        self.controller_views[interaction.guild.id] = view

    @app_commands.command(name="play", description="播放音樂（URL 或搜尋關鍵字）")
    @app_commands.describe(query="歌曲名稱 or URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        await self.play_search(interaction, query)

    @app_commands.command(name="pause", description="暫停/繼續播放")
    async def pause(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("沒有播放中的音樂"), ephemeral=True,
            )
        await player.pause(not player.paused)
        status = "⏸️ 已暫停" if player.paused else "▶️ 繼續播放"
        await interaction.response.send_message(embed=EmbedFactory.success(status))
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="skip", description="跳過當前曲目")
    async def skip(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.playing:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("沒有播放中的音樂"), ephemeral=True,
            )
        await player.skip()
        await interaction.response.send_message(embed=EmbedFactory.success("⏭️ 已跳過"))
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="stop", description="停止播放並清除佇列")
    async def stop(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("Bot 不在語音頻道中"), ephemeral=True,
            )
        await player.disconnect()
        await interaction.response.send_message(embed=EmbedFactory.success("⏹️ 已停止播放"))

    @app_commands.command(name="nowplaying", description="顯示正在播放的曲目")
    async def nowplaying(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.current:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("沒有播放中的音樂"), ephemeral=True,
            )
        track = player.current
        requester_id = getattr(track.extras, "requester_id", None) if track.extras else None
        requester = interaction.guild.get_member(requester_id) if requester_id else None
        embed = EmbedFactory.now_playing(
            title=track.title,
            url=track.uri,
            duration=self._format_duration(track.length),
            position="0:00",
            requester=requester,
            thumbnail=track.artwork,
            progress=0.0,
        )
        view = MusicPlayerView(self, owner_id=interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="queue", description="顯示播放佇列")
    async def queue_cmd(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("Bot 不在語音頻道中"), ephemeral=True,
            )
        if not player.queue and not player.current:
            return await interaction.response.send_message(
                embed=EmbedFactory.info("佇列為空", "目前沒有任何歌曲在佇列中。"), ephemeral=True,
            )

        tracks_per_page = 10
        queue_list = list(player.queue)
        pages = []
        total_pages = max(1, (len(queue_list) + tracks_per_page - 1) // tracks_per_page)

        for page_num in range(total_pages):
            start = page_num * tracks_per_page
            end = start + tracks_per_page
            page_tracks = queue_list[start:end]
            track_infos = [
                f"**{t.title}** — `{self._format_duration(t.length)}`"
                for t in page_tracks
            ]
            now_playing = player.current.title if player.current else ""
            embed = EmbedFactory.queue_page(track_infos, page_num + 1, total_pages, now_playing)
            pages.append(embed)

        if len(pages) == 1:
            await interaction.response.send_message(embed=pages[0])
        else:
            view = PaginatorView(pages, interaction.user.id)
            await interaction.response.send_message(embed=pages[0], view=view)

    @app_commands.command(name="volume", description="調整音量")
    @app_commands.describe(level="音量 (0-100)")
    async def volume_cmd(self, interaction: discord.Interaction, level: int):
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("Bot 不在語音頻道中"), ephemeral=True,
            )
        is_pro = await self.bot.db.is_guild_pro(interaction.guild_id)
        max_vol = 5000 if is_pro else 100
        
        if level < 0 or level > max_vol:
            if not is_pro:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("音量超出限制", "❌ 免費版限制音量範圍為 `0-100`。升級 Pro 專業版可解鎖最高 `5000` 音量！"),
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    embed=EmbedFactory.error("音量超出限制", "❌ 音量範圍必須在 `0` 到 `5000` 之間！"),
                    ephemeral=True
                )

        await player.set_volume(level)
        if level <= 100:
            bar_filled = max(0, min(10, int(level / 10)))
        else:
            bar_filled = max(0, min(10, int(level / 500)))
        bar = "▰" * bar_filled + "▱" * (10 - bar_filled)
        await interaction.response.send_message(
            embed=EmbedFactory.success(f"{Emoji.VOLUME} 音量", f"`{bar}` **{level}%**")
        )
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="shuffle", description="隨機排列佇列")
    async def shuffle_cmd(self, interaction: discord.Interaction):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.queue:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("佇列為空"), ephemeral=True,
            )
        player.queue.shuffle()
        await interaction.response.send_message(embed=EmbedFactory.success("🔀 佇列已隨機排列"))
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="loop", description="循環模式")
    @app_commands.choices(mode=[
        app_commands.Choice(name="關閉", value="off"),
        app_commands.Choice(name="單曲循環", value="one"),
        app_commands.Choice(name="佇列循環", value="all"),
    ])
    async def loop_cmd(self, interaction: discord.Interaction, mode: str = "off"):
        pro_cog = self.bot.cogs.get("Pro")
        if pro_cog and not await pro_cog.check_pro(interaction):
            return
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("Bot 不在語音頻道中"), ephemeral=True,
            )
        if mode == "one":
            player.queue.mode = wavelink.QueueMode.loop
            await interaction.response.send_message(embed=EmbedFactory.success("🔂 單曲循環已開啟"))
        elif mode == "all":
            player.queue.mode = wavelink.QueueMode.loop_all
            await interaction.response.send_message(embed=EmbedFactory.success("🔁 佇列循環已開啟"))
        else:
            player.queue.mode = wavelink.QueueMode.normal
            await interaction.response.send_message(embed=EmbedFactory.success("循環模式已關閉"))
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="seek", description="跳轉到指定時間（秒）")
    @app_commands.describe(position="時間位置（秒）")
    async def seek_cmd(self, interaction: discord.Interaction, position: int):
        player: wavelink.Player = interaction.guild.voice_client
        if not player or not player.current:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("沒有播放中的音樂"), ephemeral=True,
            )
        # position converted to milliseconds
        pos_ms = position * 1000
        if pos_ms < 0 or pos_ms > player.current.length:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("無效的時間", f"請輸入 0 到 {player.current.length // 1000} 秒之間的值。"),
                ephemeral=True
            )
        await player.seek(pos_ms)
        await interaction.response.send_message(
            embed=EmbedFactory.success("播放控制", f"🕒 已跳轉至 `{self._format_duration(pos_ms)}`")
        )
        await self.update_controller_message(interaction.guild)

    @app_commands.command(name="filter", description="套用高級音訊濾波器 (Ultra 專屬)")
    @app_commands.choices(choice=[
        app_commands.Choice(name="關閉 (None)", value="off"),
        app_commands.Choice(name="重低音 (Bass Boost)", value="bassboost"),
        app_commands.Choice(name="Nightcore (加快/高音)", value="nightcore"),
        app_commands.Choice(name="8D 環繞音效 (Rotation)", value="rotation"),
        app_commands.Choice(name="柔和低通 (Low Pass)", value="lowpass"),
        app_commands.Choice(name="卡拉OK (Karaoke)", value="karaoke"),
    ])
    async def filter_cmd(self, interaction: discord.Interaction, choice: str):
        # 1. 檢查是否為 Ultra
        ultra_cog = self.bot.cogs.get("Ultra")
        if ultra_cog and not await ultra_cog.check_ultra(interaction):
            return

        await interaction.response.defer()
        player: wavelink.Player = interaction.guild.voice_client
        if not player:
            return await interaction.followup.send(
                embed=EmbedFactory.error("Bot 不在語音頻道中")
            )

        filters = wavelink.Filters()
        
        if choice == "off":
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已關閉所有音訊濾波器。")
        elif choice == "bassboost":
            # 增強低音波段 (band 0-4)
            filters.equalizer.set(bands=[
                {"band": 0, "gain": 0.25},
                {"band": 1, "gain": 0.25},
                {"band": 2, "gain": 0.20},
                {"band": 3, "gain": 0.15},
                {"band": 4, "gain": 0.10}
            ])
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已成功套用 **重低音 (Bass Boost)** 濾波器！")
        elif choice == "nightcore":
            filters.timescale.set(speed=1.2, pitch=1.2)
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已成功套用 **Nightcore** 濾波器！ (速度與音調提高 20%)")
        elif choice == "rotation":
            filters.rotation.set(rotation_hz=0.2)
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已成功套用 **8D 環繞音效 (Rotation)** 濾波器！")
        elif choice == "lowpass":
            filters.low_pass.set(smoothing=20.0)
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已成功套用 **柔和低通 (Low Pass)** 濾波器！")
        elif choice == "karaoke":
            filters.karaoke.set(level=1.0)
            await player.set_filters(filters)
            embed = EmbedFactory.success("濾波器設定", "已成功套用 **卡拉OK (Karaoke)** 濾波器！")
            
        await interaction.followup.send(embed=embed)

    # ─── Wavelink 事件監聽器 ───────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player = payload.player
        if not player:
            return
        # 取消閒置斷線計時
        if hasattr(player, "idle_task") and player.idle_task:
            player.idle_task.cancel()
            player.idle_task = None
        await self.update_controller_message(player.guild)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player = payload.player
        if not player:
            return
        track = payload.track

        # 處理單曲與佇列循環
        if player.queue.mode == wavelink.QueueMode.loop:
            await player.play(track)
            return
        elif player.queue.mode == wavelink.QueueMode.loop_all:
            await player.queue.put_wait(track)

        # 播放下一首
        if not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)
        else:
            # 閒置斷線
            if not getattr(player, "mode_247", False):
                if hasattr(player, "idle_task") and player.idle_task:
                    player.idle_task.cancel()
                player.idle_task = asyncio.create_task(self._idle_disconnect(player))
        
        await self.update_controller_message(player.guild)

    async def _idle_disconnect(self, player: wavelink.Player):
        """閒置 5 分鐘後自動退出"""
        await asyncio.sleep(300)
        if not player.playing and not getattr(player, "mode_247", False):
            await player.disconnect()
            await self.update_controller_message(player.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """當 bot 被踢出頻道時清理"""
        if member.id != self.bot.user.id:
            return
        if before.channel and not after.channel:
            player = member.guild.voice_client
            if isinstance(player, wavelink.Player):
                player.queue.clear()
                if hasattr(player, "idle_task") and player.idle_task:
                    player.idle_task.cancel()
            await self.update_controller_message(member.guild)
            self.controllers.pop(member.guild.id, None)
            self.controller_views.pop(member.guild.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
