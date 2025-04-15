import discord
from discord import app_commands
from discord.ext import commands
import yfinance as yf
import mplfinance as mpf
import asyncio
import io
import pandas as pd
import matplotlib.pyplot as plt

class ChartCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        plt.switch_backend('Agg')  # Non-interactive backend

    async def period_autocomplete(self, interaction: discord.Interaction, current: str):
        periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "ytd"]
        return [app_commands.Choice(name=opt, value=opt) for opt in periods]

    async def interval_autocomplete(self, interaction: discord.Interaction, current: str):
        intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
        return [app_commands.Choice(name=opt, value=opt) for opt in intervals]

    @app_commands.command(name="chart", description="Generate trading chart")
    @app_commands.describe(
        ticker="Stock/crypto symbol",
        period="Time period",
        interval="Chart interval"
    )
    @app_commands.autocomplete(period=period_autocomplete, interval=interval_autocomplete)
    async def chart(self, interaction: discord.Interaction, 
                   ticker: str, 
                   period: str = "1d",
                   interval: str = "5m"):
        await interaction.response.defer()
        
        try:
            # Handle YTD special case
            if period == "ytd":
                period, interval = "ytd", "1d"

            # Async data fetch
            async def fetch_data():
                return await asyncio.to_thread(
                    lambda: yf.download(
                        tickers=ticker,
                        period=period,
                        interval=interval,
                        progress=False,
                        auto_adjust=True
                    )
                )

            data = await asyncio.wait_for(fetch_data(), timeout=15)
            
            # Validate data
            if data.empty:
                embed = discord.Embed(
                    title="❌ No Data",
                    description=f"No valid data found for {ticker.upper()}",
                    color=0xE74C3C
                )
                return await interaction.followup.send(embed=embed)

            # Clean data
            data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            price_cols = ['Open', 'High', 'Low', 'Close']
            data[price_cols] = data[price_cols].apply(pd.to_numeric, errors='coerce')
            data = data.dropna()

            # Generate chart
            def create_chart():
                plt.style.use('dark_background')
                mc = mpf.make_marketcolors(
                    up='#C0392B',
                    down='#27AE60',
                    edge='transparent',
                    wick={'up': '#27AE60', 'down': '#C0392B'},
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
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', facecolor='#031125', dpi=100)
                plt.close(fig)
                buf.seek(0)
                return buf

            # Generate and send chart
            chart = await asyncio.to_thread(create_chart)
            embed = discord.Embed(
                title=f"📊 {ticker.upper()} Chart",
                description="",
                color=0x1ABC9C
            )
            embed.set_image(url="attachment://chart.png")
            await interaction.followup.send(
                embed=embed,
                file=discord.File(chart, "chart.png")
            )
            chart.close()

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏰ Timeout",
                description="Data fetch took too long",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Chart Error",
                description=f"``````",  # Truncate long errors
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ChartCog(bot))
