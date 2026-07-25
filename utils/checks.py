"""
權限檢查裝飾器
用於管理指令的權限驗證
"""

import discord
from discord.ext import commands
from discord import app_commands
from config import OWNER_ID


def is_admin():
    """檢查是否為管理員"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


def is_mod():
    """檢查是否有管理成員權限"""
    async def predicate(interaction: discord.Interaction) -> bool:
        perms = interaction.user.guild_permissions
        return (
            perms.administrator
            or perms.manage_guild
            or perms.kick_members
            or perms.ban_members
            or perms.moderate_members
        )
    return app_commands.check(predicate)


def is_owner():
    """檢查是否為 Bot 擁有者"""
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == OWNER_ID or interaction.user.id == 1437408048934027274
    return app_commands.check(predicate)


def has_any_permission(**perms):
    """檢查是否有任意指定權限"""
    async def predicate(interaction: discord.Interaction) -> bool:
        user_perms = interaction.user.guild_permissions
        return any(getattr(user_perms, perm, False) for perm in perms)
    return app_commands.check(predicate)


def check_member_hierarchy(author: discord.Member, target: discord.Member, me: discord.Member) -> tuple[bool, str | None]:
    """檢查成員階層是否允許操作，回傳 (是否允許, 原因)"""
    if author.id == author.guild.owner_id:
        if author.id == target.id:
            return False, "您不能對自己執行此操作。"
        return True, None
        
    if target.id == author.guild.owner_id:
        return False, "無法執行操作：目標成員是伺服器擁有者。"
        
    if author.id == target.id:
        return False, "您不能對自己執行此操作。"

    if target.top_role > author.top_role:
        return False, f"無法執行操作：目標成員的最高身份組 ({target.top_role.name}) 權限高於您的最高身份組 ({author.top_role.name})。"
        
    if target.top_role == author.top_role:
        return False, f"無法執行操作：目標成員的最高身份組 ({target.top_role.name}) 與您的最高身份組 ({author.top_role.name}) 權限相同。"
        
    if target.top_role >= me.top_role:
        return False, f"無法執行操作：目標成員的最高身份組 ({target.top_role.name}) 權限高於或等於 Bot 的最高身份組 ({me.top_role.name})。"
        
    return True, None


async def check_hierarchy(interaction: discord.Interaction, target: discord.Member) -> tuple[bool, str | None]:
    """檢查角色階層是否允許操作，回傳 (是否允許, 原因)"""
    guild = interaction.guild
    author = interaction.user
    me = guild.me
    return check_member_hierarchy(author, target, me)
