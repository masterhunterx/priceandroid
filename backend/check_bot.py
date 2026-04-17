"""
Script de diagnóstico del Bot de Discord.
Ejecutar manualmente para verificar que el bot se conecta correctamente.
El token se obtiene desde la variable de entorno DISCORD_BOT_TOKEN.
"""
import os
from dotenv import load_dotenv
load_dotenv()

import discord

token = os.environ.get("DISCORD_BOT_TOKEN")
if not token:
    print("ERROR: DISCORD_BOT_TOKEN no está configurado en las variables de entorno.")
    exit(1)

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Conectado como {bot.user}")
    print(f"Bot presente en {len(bot.guilds)} servidores.")
    for g in bot.guilds:
        print(f" - {g.name} (id: {g.id}) | Members: {g.member_count}")
    await bot.close()

bot.run(token)
