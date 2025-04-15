import discord
from discord import app_commands
from discord.ext import commands
import yfinance as yf
import datetime

class StockCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stock", description="Get stock market data")
    @app_commands.describe(ticker="Stock/crypto symbol")
    async def stock(self, interaction: discord.Interaction, ticker: str):
        await interaction.response.defer()
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="1m")
            
            if hist.empty:
                embed = discord.Embed(
                    title="❌ Invalid Ticker",
                    description=f"Couldn't find data for {ticker.upper()}",
                    color=0xE74C3C
                )
                return await interaction.followup.send(embed=embed)

            latest = hist.iloc[-1]
            change = ((latest["Close"] - hist.iloc[0]["Open"]) / hist.iloc[0]["Open"]) * 100
            trend = "📈" if change >= 0 else "📉"

            embed = discord.Embed(
                title=f"{trend} {ticker.upper()}",
                color=0x2ECC71 if change >= 0 else 0xE74C3C,
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Price", value=f"${latest['Close']:.2f}", inline=True)
            embed.add_field(name="Change", value=f"{change:+.2f}%", inline=True)
            embed.add_field(name="Volume", value=f"{latest['Volume']:,}", inline=False)
            embed.add_field(name="Open", value=f"${hist.iloc[0]['Open']:.2f}", inline=True)
            embed.add_field(name="High", value=f"${latest['High']:.2f}", inline=True)
            embed.add_field(name="Low", value=f"${latest['Low']:.2f}", inline=True)
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Stock Error",
                description=f"``````",
                color=0xE74C3C
            )
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(StockCog(bot))
