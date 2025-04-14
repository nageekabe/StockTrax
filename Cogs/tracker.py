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
from PIL import Image, ImageFilter  # Added Pillow imports

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_announcement.start()
        self.channel_id = None
        self.tracker = {}
        self.bot.loop.create_task(self.load_config())
        plt.switch_backend('Agg')

    def cog_unload(self):
        self.update_announcement.cancel()

    # ... (keep existing save_config, load_config, cleanup_messages methods unchanged) ...

    async def update_or_create_message(self, symbol):
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            return None

        try:
            message = None
            if symbol in self.tracker and self.tracker[symbol]:
                try:
                    message = await channel.fetch_message(self.tracker[symbol])
                except discord.NotFound:
                    self.tracker[symbol] = None

            stock = yf.Ticker(symbol)
            hist = stock.history(period="1d", interval="1m")
            
            if not hist.empty:
                hist = hist[['Open', 'High', 'Low', 'Close', 'Volume']]
                hist.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                hist = hist.dropna()
                
                latest = hist.iloc[-1]
                change = ((latest["Close"] - hist.iloc[0]["Open"]) / hist.iloc[0]["Open"]) * 100
                trend = "📈" if change >= 0 else "📉"
                
                # Generate dual-resolution images
                thumb_buf, full_buf = await asyncio.to_thread(
                    self.generate_dual_resolution_charts, hist
                )

                # Create sharpened thumbnail
                sharp_thumb = await asyncio.to_thread(
                    self.sharpen_image, thumb_buf
                )
                
                # Create Discord files
                thumb_file = discord.File(sharp_thumb, filename=f"{symbol}_thumb.webp")
                full_file = discord.File(full_buf, filename=f"{symbol}_full.webp")
                
                embed = discord.Embed(
                    title=f"{trend} {symbol}",
                    color=0x1ABC9C,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="Price", value=f"${latest['Close']:.2f}", inline=True)
                embed.add_field(name="Change", value=f"{change:+.2f}%", inline=True)
                embed.set_image(url=f"attachment://{symbol}_thumb.webp")
                embed.set_footer(text="Click image for full resolution • Updates every minute")
                
                if not message:
                    message = await channel.send(embed=embed, files=[full_file, thumb_file])
                    self.tracker[symbol] = message.id
                else:
                    await message.edit(embed=embed, attachments=[full_file, thumb_file])
                
                # Close buffers
                thumb_buf.close()
                full_buf.close()
                sharp_thumb.close()

        except Exception as e:
            print(f"Error processing {symbol}: {str(e)}")
        return None

    def generate_dual_resolution_charts(self, data):
        """Generate both thumbnail and full-size charts"""
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
        
        # Thumbnail (small preview)
        fig_thumb, _ = mpf.plot(
            data,
            type='candle',
            style=s,
            volume=False,
            returnfig=True,
            figsize=(3, 1.5),  # Smaller dimensions
            axisoff=True,
            scale_padding=0.1,
            tight_layout=True
        )
        thumb_buf = io.BytesIO()
        fig_thumb.savefig(
            thumb_buf,
            format='webp',
            dpi=100,  # Lower DPI for small size
            bbox_inches='tight',
            pad_inches=0.1,
            facecolor='#031125'
        )
        plt.close(fig_thumb)
        thumb_buf.seek(0)

        # Full-size (click-to-view)
        fig_full, _ = mpf.plot(
            data,
            type='candle',
            style=s,
            volume=False,
            returnfig=True,
            figsize=(10, 5),  # Larger dimensions
            axisoff=True,
            scale_padding=0.1,
            tight_layout=True
        )
        full_buf = io.BytesIO()
        fig_full.savefig(
            full_buf,
            format='webp',
            dpi=300,  # Higher DPI for detail
            bbox_inches='tight',
            pad_inches=0.1,
            facecolor='#031125'
        )
        plt.close(fig_full)
        full_buf.seek(0)

        return thumb_buf, full_buf

    def sharpen_image(self, image_buffer):
        """Apply sharpening to reduce blur in thumbnails"""
        img = Image.open(image_buffer)
        img = img.filter(ImageFilter.SHARPEN)
        sharp_buf = io.BytesIO()
        img.save(sharp_buf, format='webp', quality=95)
        sharp_buf.seek(0)
        return sharp_buf

    # ... (keep rest of the class methods unchanged) ...

async def setup(bot):
    await bot.add_cog(Tracker(bot))
