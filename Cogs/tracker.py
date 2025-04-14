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

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_announcement.start()
        self.channel_id = None
        self.tracker = {}  # {ticker: message_id}
        self.bot.loop.create_task(self.load_config())
        plt.switch_backend('Agg')

    def cog_unload(self):
        self.update_announcement.cancel()

    async def save_config(self):
        config = {
            "channel_id": self.channel_id,
            "tracker": self.tracker
        }
        await asyncio.to_thread(
            lambda: json.dump(config, open("announcements_config.json", "w"))
        )

    async def load_config(self):
        try:
            if os.path.exists("announcements_config.json"):
                config = await asyncio.to_thread(
                    lambda: json.load(open("announcements_config.json", "r"))
                )
                self.channel_id = config.get("channel_id")
                self.tracker = config.get("tracker", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.tracker = {}
            await self.save_config()

    async def update_or_create_message(self, symbol):
        """Create new message or update existing one"""
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return None

        try:
            message = None
            # Try to fetch existing message
            if symbol in self.tracker and self.tracker[symbol]:
                try:
                    message = await channel.fetch_message(self.tracker[symbol])
                except discord.NotFound:
                    self.tracker[symbol] = None

            # Generate new content
            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d", interval="1m")
            
            if not hist.empty:
                hist = hist[['Open', 'High', 'Low', 'Close', 'Volume']]
                hist.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                hist = hist.dropna()
                
                latest = hist.iloc[-1]
                change = ((latest["Close"] - hist.iloc[0]["Open"]) / hist.iloc[0]["Open"]) * 100
                trend = "📈" if change >= 0 else "📉"
                
                # Generate mini-chart
                chart = await asyncio.to_thread(
                    lambda: self.generate_mini_chart(hist)
                )
                # Create discord file

                #Create embed with file
                embed = discord.Embed(
                    title=f"{trend} {symbol}",
                    color=0x1ABC9C,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Price", value=f"${latest['Close']:.2f}", inline=True)
                embed.add_field(name="Change", value=f"{change:+.2f}%", inline=True)
                embed.set_image(url=f"attachment://{symbol}.png")
                embed.set_footer(text="Click image for full resolution • Updates every minute")
                
                # Create new message if missing
                if not message:
                    file = discord.File(chart, filename=f"{symbol}.png")
                    message = await channel.send(embed=embed, file=file)
                    self.tracker[symbol] = message.id
                else:
                     chart.seek(0)
                     file = discord.File(chart, filename=f"{symbol}.png")
                     await message.edit(embed=embed, attachments=[file])
                    
                chart.close()
                return message

        except Exception as e:
            print(f"Error processing {symbol}: {str(e)}")
        return None

    async def cleanup_messages(self):
        """Delete messages for removed tickers"""
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return

        current_tickers = set(self.tracker.keys())
        configured_tickers = set(self.get_tickers())

        for symbol in (current_tickers - configured_tickers):
            try:
                if self.tracker[symbol]:
                    message = await channel.fetch_message(self.tracker[symbol])
                    await message.delete()
            except discord.NotFound:
                pass
            del self.tracker[symbol]

    def generate_mini_chart(self, data):
        """Generate compact 100x50 pixel chart"""
        plt.style.use('dark_background')
        mc = mpf.make_marketcolors(
            up='#27AE60',
            down='#C0392B',
            edge='#BDC3C7',
            wick={'up': '#27AE60', 'down': '#C0392B'}
        )
        s = mpf.make_mpf_style(
            base_mpl_style='dark_background',
            marketcolors=mc,
            gridstyle='',
            facecolor='#031125'
        )
        
        fig, _ = mpf.plot(
            data,
            type='candle',
            style=s,
            volume=False,
            returnfig=True,
            figsize=(5, 2.5),
            axisoff=True,
            closefig=True,
            scale_padding=0.1,
        )
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format='png',
            bbox_inches='tight',
            pad_inches=0.1,
            facecolor='#031125',
            dpi=50,
            transparent=False
        )
        plt.close(fig)
        buf.seek(0)
        return buf

    @tasks.loop(minutes=1)
    async def update_announcement(self):
        if not self.channel_id:
            return

        # Update existing tickers
        for symbol in self.get_tickers():
            await self.update_or_create_message(symbol)

        # Cleanup removed tickers
        await self.cleanup_messages()
        await self.save_config()

    def get_tickers(self):
        """Get currently configured tickers"""
        return list(self.tracker.keys())

    @update_announcement.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def set_announcement_channel(self, ctx, channel: discord.TextChannel):
        """Set channel for live updates"""
        await ctx.defer()
        
        try:
            self.channel_id = channel.id
            await self.save_config()
            
            embed = discord.Embed(
                title="✅ Channel Configured",
                description=f"Announcements will now appear in {channel.mention}",
                color=0x2ECC71
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Configuration Error",
                description=f"``````",
                color=0xE74C3C
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def add_ticker(self, ctx, symbol: str):
        """Add symbol to watchlist"""
        await ctx.defer()
        
        try:
            symbol = symbol.upper()
            if symbol in self.tracker:
                embed = discord.Embed(
                    title="⚠️ Exists",
                    description=f"{symbol} already in watchlist",
                    color=0xF1C40F
                )
            else:
                self.tracker[symbol] = None  # Will be set on first update
                await self.save_config()
                embed = discord.Embed(
                    title="✅ Added",
                    description=f"{symbol} added to watchlist",
                    color=0x2ECC71
                )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Add Error",
                description=f"``````",
                color=0xE74C3C
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.has_permissions(manage_guild=True)
    async def remove_ticker(self, ctx, symbol: str):
        """Remove symbol from watchlist"""
        await ctx.defer()
        
        try:
            symbol = symbol.upper()
            if symbol in self.tracker:
                del self.tracker[symbol]
                await self.save_config()
                embed = discord.Embed(
                    title="✅ Removed",
                    description=f"{symbol} removed from watchlist",
                    color=0x2ECC71
                )
            else:
                embed = discord.Embed(
                    title="⚠️ Not Found",
                    description=f"{symbol} not in watchlist",
                    color=0xE74C3C
                )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Remove Error",
                description=f"``````",
                color=0xE74C3C
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Tracker(bot))
