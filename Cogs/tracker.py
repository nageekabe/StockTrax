import discord
from discord.ext import commands, tasks
import yfinance as yf
import asyncio
import datetime
import json
import os
import mplfinance as mpf
import pandas as pd
import matplotlib.pyplot as plt
import io
from PIL import Image, ImageFilter

class StockTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_announcement.start()
        self.server_configs = {}
        self.bot.loop.create_task(self.load_configs())
        plt.switch_backend('Agg')

    async def load_configs(self):
        """Load server configurations"""
        try:
            if os.path.exists("server_configs.json"):
                with open("server_configs.json", "r") as f:
                    self.server_configs = json.load(f)
        except Exception:
            self.server_configs = {}

    async def save_configs(self):
        """Save server configurations"""
        with open("server_configs.json", "w") as f:
            json.dump(self.server_configs, f)

    async def update_or_create_message(self, guild_id, symbol):
        """Handle message updates with optimized quality"""
        config = self.server_configs.get(str(guild_id), {})
        if not config.get("channel_id"):
            return

        channel = self.bot.get_channel(config["channel_id"])
        if not channel:
            return

        try:
            message = None
            tracker = config["tracker"]
            
            if symbol in tracker and tracker[symbol]:
                try:
                    message = await channel.fetch_message(tracker[symbol])
                except discord.NotFound:
                    tracker[symbol] = None

            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d", interval="1m")
            
            if not hist.empty:
                hist = hist[['Open', 'High', 'Low', 'Close', 'Volume']]
                hist = hist.dropna()
                
                latest = hist.iloc[-1]
                change = ((latest["Close"] - hist.iloc[0]["Open"]) / hist.iloc[0]["Open"]) * 100
                trend = "📈" if change >= 0 else "📉"
                
                # Generate optimized WebP chart
                chart_buffer = await asyncio.to_thread(
                    self.generate_webp_chart, hist
                )
                
                # Create Discord file
                file = discord.File(chart_buffer, filename=f"{symbol}.webp")
                
                # Build embed
                embed = discord.Embed(
                    title=f"{trend} {symbol}",
                    color=0x1ABC9C,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Price", value=f"${latest['Close']:.2f}", inline=True)
                embed.add_field(name="Change", value=f"{change:+.2f}%", inline=True)
                embed.set_image(url=f"attachment://{symbol}.webp")
                embed.set_footer(text="Click image for full resolution • Updates every minute")

                # Update or create message
                if not message:
                    message = await channel.send(embed=embed, file=file)
                    tracker[symbol] = message.id
                else:
                    await message.edit(embed=embed, attachments=[file])
                
                chart_buffer.close()

        except Exception as e:
            print(f"Error processing {symbol}: {str(e)}")

    def generate_webp_chart(self, data):
        """Generate high-quality WebP chart"""
        plt.style.use('dark_background')
        mc = mpf.make_marketcolors(
            up='#27AE60', down='#C0392B',
            edge='#BDC3C7', wick={'up': '#27AE60', 'down': '#C0392B'}
        )
        style = mpf.make_mpf_style(
            base_mpl_style='dark_background',
            marketcolors=mc,
            gridstyle='',
            facecolor='#031125'
        )

        fig, _ = mpf.plot(
            data,
            type='candle',
            style=style,
            volume=False,
            returnfig=True,
            figsize=(10, 5),
            axisoff=True,
            scale_padding=0.1,
            tight_layout=True
        )
        
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format='webp',
            dpi=200,
            bbox_inches='tight',
            pad_inches=0.1,
            facecolor='#031125',
            quality=95
        )
        plt.close(fig)
        buf.seek(0)
        return buf

    @tasks.loop(minutes=1)
    async def update_announcement(self):
        """Update all tracked symbols"""
        for guild_id, config in self.server_configs.items():
            for symbol in config["tracker"].keys():
                await self.update_or_create_message(guild_id, symbol)

    @update_announcement.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set announcement channel"""
        guild_id = str(ctx.guild.id)
        self.server_configs[guild_id] = {
            "channel_id": channel.id,
            "tracker": {}
        }
        await self.save_configs()
        await ctx.send(f"✅ Announcements will appear in {channel.mention}")

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def add_ticker(self, ctx, symbol: str):
        """Add stock to track"""
        guild_id = str(ctx.guild.id)
        symbol = symbol.upper()
        
        if guild_id not in self.server_configs:
            await ctx.send("❌ Set a channel first!")
            return
            
        if symbol in self.server_configs[guild_id]["tracker"]:
            await ctx.send(f"⚠️ {symbol} already tracked!")
            return
            
        self.server_configs[guild_id]["tracker"][symbol] = None
        await self.save_configs()
        await ctx.send(f"✅ Added {symbol} to watchlist")

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def remove_ticker(self, ctx, symbol: str):
        """Remove stock from tracking"""
        guild_id = str(ctx.guild.id)
        symbol = symbol.upper()
        
        if guild_id in self.server_configs and symbol in self.server_configs[guild_id]["tracker"]:
            del self.server_configs[guild_id]["tracker"][symbol]
            await self.save_configs()
            await ctx.send(f"✅ Removed {symbol} from watchlist")
        else:
            await ctx.send(f"⚠️ {symbol} not found!")

async def setup(bot):
    await bot.add_cog(StockTracker(bot))
