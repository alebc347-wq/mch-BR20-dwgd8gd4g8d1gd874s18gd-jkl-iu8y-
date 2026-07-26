import discord
import inspect

client = discord.Client(intents=discord.Intents.default())
try:
    print(inspect.getsource(client.on_interaction))
except Exception as e:
    print("ERROR:", e)
