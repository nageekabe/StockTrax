import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()

# Configure intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    help_command=None
)

async def load_cogs():
    try:
        await bot.load_extension("Cogs.stock")
        await bot.load_extension("Cogs.graph")
        await bot.load_extension("Cogs.tracker")
        print("✅ Cogs loaded successfully!")
    except Exception as e:
        print(f"❌ Error loading cogs: {e}")

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    await load_cogs()
    
    # Critical: Sync commands to current guild
    try:
        synced = await bot.tree.sync()
        print(f"🔗 Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Sync error: {e}")

async def main():
    async with bot:
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    # Windows-compatible event loop
    loop = asyncio.get_event_loop()
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n👋 Manual shutdown complete")
    except Exception as e:
        print(f"🔥 Fatal error: {e}")
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
