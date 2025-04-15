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
        except Exception as e:
            print(f"Config load error: {e}")
            self.server_configs = {}

    async def save_configs(self):
        """Save server configurations"""
        try:
            with open("server_configs.json", "w") as f:
                json.dump(self.server_configs, f)
        except Exception as e:
            print(f"Config save error: {e}")

    async def update_or_create_message(self, guild_id, symbol):
        """Handle message updates with proper daily % calculation"""
        config = self.server_configs.get(str(guild_id), {})
        if not config.get("channel_id"):
            return

        channel = self.bot.get_channel(int(config["channel_id"]))
        if not channel:
            return

        try:
            message = None
            tracker = config["tracker"]
            
            if symbol in tracker and tracker[symbol]:
                try:
                    message = await channel.fetch_message(int(tracker[symbol]))
                except discord.NotFound:
                    tracker[symbol] = None
                except discord.Forbidden:
                    print(f"Missing permissions in channel {channel.id}")
                    return

            stock = yf.Ticker(symbol)
            
            # Get separate datasets
            try:
                intraday_data = stock.history(period="1d", interval="5m")
                daily_data = stock.history(period="2d", interval="1d")
            except Exception as e:
                print(f"YFinance error for {symbol}: {str(e)}")
                return

            # Validate data exists
            if intraday_data.empty or len(daily_data) < 2:
                print(f"No sufficient data for {symbol}")
                return
                
            # Calculate daily percentage change
            previous_close = daily_data.iloc[0]["Close"]
            current_price = intraday_data.iloc[-1]["Close"]
            daily_change = ((current_price - previous_close) / previous_close) * 100
            print(daily_data, intraday_data)
            print(previous_close, current_price)
            
            trend, newcolor = ("📈", [46, 204, 113]) if daily_change >= 0 else ("📉", [231, 76, 60])
            
            # Generate optimized WebP chart
            chart_buffer = await asyncio.to_thread(
                self.generate_webp_chart, intraday_data
            )
            
            # Create Discord file
            file = discord.File(chart_buffer, filename=f"HD_{symbol}.webp")
            
            # Build embed
            embed = discord.Embed(
                title=f"{trend} {symbol}",
                color=discord.Color.from_rgb(newcolor[0], newcolor[1], newcolor[2]),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="Price", value=f"**``${current_price:.2f}``**", inline=True)
            embed.add_field(name="Change", value=f"**``{daily_change:+.2f}%``**", inline=True)
            embed.set_image(url=f"attachment://HD_{symbol}.webp")
            embed.set_footer(text="Click image for full resolution • Updates every minute")

            # Update or create message
            if not message:
                message = await channel.send(embed=embed, file=file)
                tracker[symbol] = str(message.id)
            else:
                await message.edit(embed=embed, attachments=[file])
            
            chart_buffer.close()

        except Exception as e:
            print(f"Error processing {symbol}: {str(e)}")

    def generate_webp_chart(self, data):
        """Generate high-quality WebP chart"""
        plt.style.use('dark_background')
        mc = mpf.make_marketcolors(
            up='#C0392B',
            down='#27AE60',
            wick={'up': '#C0392B', 'down': '#27AE60'},
            volume='in',
        )
        s = mpf.make_mpf_style(
            base_mpl_style='dark_background',
            marketcolors=mc,
            gridstyle='--',
            gridcolor='#2C3E50',
            facecolor='#031125'
        )
        fig, _ = mpf.plot(
            data,
            type='candle',
            mav=(3, 21, 43),
            style=s,
            ylabel='',
            volume=False,
            returnfig=True,
            figsize=(12,6),
            closefig=True  # Ensure figure is closed after plotting
        )
        
        # Generate WebP with maximum quality
        buf = io.BytesIO()
        fig.savefig(
            buf,
            format='webp',
            dpi=300,
            bbox_inches='tight',
            pad_inches=0.1,
            facecolor='#031125',
            pil_kwargs={'quality': 95}
        )
        plt.close(fig)
        buf.seek(0)
        return buf

    @tasks.loop(minutes=1)
    async def update_announcement(self):
        """Update all tracked symbols"""
        if not self.server_configs:
            return
            
        for guild_id, config in self.server_configs.items():
            if not config.get("tracker"):
                continue
                
            for symbol in config["tracker"].keys():
                await self.update_or_create_message(guild_id, symbol)
            await self.save_configs()

    @update_announcement.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set announcement channel"""
        guild_id = str(ctx.guild.id)
        self.server_configs[guild_id] = {
            "channel_id": str(channel.id),
            "tracker": {}
        }
        await self.save_configs()
        await ctx.send(f"✅ Announcements will appear in {channel.mention}")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def add_ticker(self, ctx, symbol: str):
        """Add stock to track"""
        guild_id = str(ctx.guild.id)
        symbol = symbol.upper()
        
        if guild_id not in self.server_configs:
            await ctx.send("❌ Set a channel first using /set_channel!")
            return
            
        if symbol in self.server_configs[guild_id]["tracker"]:
            await ctx.send(f"⚠️ {symbol} already tracked!")
            return
            
        self.server_configs[guild_id]["tracker"][symbol] = None
        await self.save_configs()
        await ctx.send(f"✅ Added {symbol} to watchlist")

    @commands.hybrid_command()
    @commands.has_permissions(administrator=True)
    async def remove_ticker(self, ctx, symbol: str):
        """Remove stock from tracking"""
        guild_id = str(ctx.guild.id)
        symbol = symbol.upper()
        
        if guild_id in self.server_configs and symbol in self.server_configs[guild_id]["tracker"]:
            message_id = self.server_configs[guild_id]["tracker"][symbol]
            channel_id = self.server_configs[guild_id]["channel_id"]
            channel = await self.bot.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
            del self.server_configs[guild_id]["tracker"][symbol]
            await self.save_configs()
            await ctx.send(f"✅ Removed {symbol} from watchlist")
        else:
            await ctx.send(f"⚠️ {symbol} not found!")

async def setup(bot):
    await bot.add_cog(StockTracker(bot))
