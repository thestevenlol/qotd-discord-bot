# question_bot/bot.py
import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv # Import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
# TEST_GUILD_ID = os.getenv("TEST_GUILD_ID") # Example if you add it

from db_manager import initialize_db # Import the DB initializer

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True
intents.members = True

class QuestionBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned_or("!q "), intents=intents)

    async def setup_hook(self):
        print("Loading cogs...")
        # Use fully qualified paths relative to the 'qotd_bot' package
        initial_extensions = [
            'cogs.config_cog',
            'cogs.questions_cog',
            'cogs.scheduler_cog'
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"Successfully loaded {extension}")
            except commands.errors.ExtensionFailed as e:
                print(f"Failed to load extension {extension}.")
                print(f"Original error: {e.original}")
            except Exception as e:
                print(f"Failed to load extension {extension}.")
                print(f"[UNEXPECTED ERROR TYPE] {type(e).__name__}: {e}")

        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} commands globally.")
        except Exception as e:
            print(f"Error syncing commands: {e}")

    async def on_ready(self):
        print(f'Logged in as {self.user.name} (ID: {self.user.id})')
        print(f'Discord.py Version: {discord.__version__}')
        print('------')
        await self.change_presence(activity=discord.Game(name="/help for commands"))

# Initialize Database
initialize_db()
print("Database initialized by bot.py.")

bot = QuestionBot()

# This __main__ block will only run if bot.py is executed directly,
# NOT when imported as part of `python -m qotd_bot.bot`.
# For `python -m qotd_bot.bot`, the execution starts from the package level.
# We need a way for the bot to run when `python -m qotd_bot.bot` is called.
# One way is to put the bot.run() outside the if __name__ == "__main__"
# OR create a __main__.py file in qotd_bot.

# For now, let's keep it simple and assume bot.py is the entry point for -m
if __name__ == "__main__": # This will be true when running 'python -m qotd_bot.bot'
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not found in .env file or environment variables.")
    else:
        try:
            print("Starting bot...")
            bot.run(BOT_TOKEN)
        except discord.LoginFailure:
            print("ERROR: Invalid Discord Bot Token. Please check your .env file.")
        except Exception as e:
            print(f"An unexpected error occurred while running the bot: {e}")