import discord
from discord import app_commands

tree = app_commands.CommandTree(discord.Client(intents=discord.Intents.default()))
print("COMMAND TREE METHODS:")
for name in dir(tree):
    if not name.startswith("__"):
        print(f"  {name}")
