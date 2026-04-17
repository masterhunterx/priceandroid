import discord
import os
from dotenv import load_dotenv

# Load config from root .env (one level up from /backend)
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(root_dir, '.env')
load_dotenv(dotenv_path=env_path)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"--- BOT DIAGNOSTIC ---")
    print(f"Logged in as: {bot.user}")
    print(f"Connected to {len(bot.guilds)} guilds.")
    for g in bot.guilds:
        print(f" - Guild: {g.name} (ID: {g.id}) | Members: {g.member_count}")
        # Check permissions in the first text channel or similar
        for channel in g.text_channels:
            perms = channel.permissions_for(g.me)
            print(f"   - Channel: {channel.name} | Read: {perms.read_messages}, Send: {perms.send_messages}, Embeds: {perms.embed_links}")
            break # just one per guild for brevity
    print(f"--- END DIAGNOSTIC ---")
    await bot.close()

if DISCORD_BOT_TOKEN:
    bot.run(DISCORD_BOT_TOKEN)
else:
    print(f"Error: DISCORD_BOT_TOKEN not found in {env_path}")
