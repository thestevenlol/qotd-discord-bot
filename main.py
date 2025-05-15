import os
import logging
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import asyncio
from dotenv import load_dotenv
from datetime import datetime, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import glob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("qotd-bot")

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Initialize bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize scheduler
scheduler = AsyncIOScheduler()

# Database setup
DB_PATH = os.getenv('DB_PATH', "qotd.db")

async def setup_database():
    """Initialize the SQLite database with required tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Create config table for storing channel settings
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channel_config (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                time TEXT NOT NULL,
                frequency TEXT NOT NULL,
                ping_role_id INTEGER,
                last_question_id INTEGER
            )
        ''')
        
        # Create packs table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS question_packs (
                pack_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, name)
            )
        ''')
        
        # Create questions table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pack_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_sent TIMESTAMP,
                times_sent INTEGER DEFAULT 0,
                FOREIGN KEY (pack_id) REFERENCES question_packs(pack_id)
            )
        ''')
        
        # Create suggestion table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS suggestions (
                suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                pack_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                suggested_by INTEGER NOT NULL,
                suggested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                FOREIGN KEY (pack_id) REFERENCES question_packs(pack_id)
            )
        ''')
        
        # Create channel_packs table for associating channels with question packs
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channel_packs (
                channel_id INTEGER NOT NULL,
                pack_id INTEGER NOT NULL,
                PRIMARY KEY (channel_id, pack_id),
                FOREIGN KEY (channel_id) REFERENCES channel_config(channel_id),
                FOREIGN KEY (pack_id) REFERENCES question_packs(pack_id)
            )
        ''')
        
        await db.commit()

@bot.event
async def on_ready():
    """Called when the bot has connected to Discord."""
    logger.info(f"{bot.user} has connected to Discord!")
    
    # Set up database
    await setup_database()
    
    # Load command cogs
    command_files = glob.glob('./commands/*.py')
    for file in command_files:
        try:
            module_name = os.path.basename(file)[:-3]  # Remove .py extension
            module_path = f'commands.{module_name}'
            await bot.load_extension(module_path)
            logger.info(f"Loaded extension: {module_path}")
        except Exception as e:
            logger.error(f"Failed to load extension {file}: {e}")
    
    # Start scheduler
    await schedule_all_questions()
    scheduler.start()
    
    # Register app commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

async def schedule_all_questions():
    """Schedule all configured questions from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM channel_config') as cursor:
            configs = await cursor.fetchall()
            
    for config in configs:
        await schedule_question(config)

async def schedule_question(config):
    """Schedule a question for a specific channel configuration."""
    channel_id = config['channel_id']
    time_str = config['time']  # Format: "HH:MM" (24-hour)
    frequency = config['frequency']  # "daily", "weekly-X" (X is day of week, 0-6)
    
    hour, minute = map(int, time_str.split(':'))
    
    if frequency == "daily":
        trigger = CronTrigger(hour=hour, minute=minute)
    elif frequency.startswith("weekly"):
        day_of_week = int(frequency.split('-')[1])
        trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
    else:
        logger.error(f"Unknown frequency: {frequency} for channel {channel_id}")
        return
    
    scheduler.add_job(
        send_scheduled_question,
        trigger=trigger,
        args=[channel_id],
        id=f"qotd_{channel_id}",
        replace_existing=True
    )
    logger.info(f"Scheduled question for channel {channel_id} at {hour}:{minute:02d}, frequency: {frequency}")

async def send_scheduled_question(channel_id):
    """Send a scheduled question to a channel."""
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)
            
        await send_question_to_channel(channel)
    except Exception as e:
        logger.error(f"Error sending scheduled question to {channel_id}: {e}")

async def send_question_to_channel(channel):
    """Send a question to the specified channel."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Get channel configuration
        async with db.execute(
            'SELECT * FROM channel_config WHERE channel_id = ?', 
            (channel.id,)
        ) as cursor:
            config = await cursor.fetchone()
            
        if not config:
            return
        
        # Get pack IDs for this channel
        async with db.execute(
            'SELECT pack_id FROM channel_packs WHERE channel_id = ?',
            (channel.id,)
        ) as cursor:
            pack_rows = await cursor.fetchall()
            pack_ids = [row['pack_id'] for row in pack_rows]
            
        if not pack_ids:
            logger.warning(f"No question packs associated with channel {channel.id}")
            return
            
        # Get a question that hasn't been sent to this channel recently
        placeholders = ','.join('?' for _ in pack_ids)
        query = f'''
            SELECT * FROM questions
            WHERE pack_id IN ({placeholders})
            AND (last_sent IS NULL OR question_id != ?)
            ORDER BY times_sent ASC, RANDOM()
            LIMIT 1
        '''
        
        params = pack_ids + [config['last_question_id'] if config['last_question_id'] else -1]
        
        async with db.execute(query, params) as cursor:
            question = await cursor.fetchone()
            
        if not question:
            # If all questions have been sent, pick the least frequently sent one
            query = f'''
                SELECT * FROM questions
                WHERE pack_id IN ({placeholders})
                ORDER BY times_sent ASC, RANDOM()
                LIMIT 1
            '''
            async with db.execute(query, pack_ids) as cursor:
                question = await cursor.fetchone()
                
        if not question:
            await channel.send("No questions available in the configured packs.")
            return
        
        # Update question usage statistics
        await db.execute(
            'UPDATE questions SET last_sent = CURRENT_TIMESTAMP, times_sent = times_sent + 1 WHERE question_id = ?',
            (question['question_id'],)
        )
        
        # Update the last question sent in channel config
        await db.execute(
            'UPDATE channel_config SET last_question_id = ? WHERE channel_id = ?',
            (question['question_id'], channel.id)
        )
        
        # Get pack info
        async with db.execute(
            'SELECT * FROM question_packs WHERE pack_id = ?',
            (question['pack_id'],)
        ) as cursor:
            pack = await cursor.fetchone()
            
        # Get ping role if configured
        ping_role = None
        if config['ping_role_id']:
            ping_role = channel.guild.get_role(config['ping_role_id'])
            
        await db.commit()
    
    # Create embed for question
    embed = discord.Embed(
        title="Question of the Day",
        description=question['content'],
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"From pack: {pack['name']}")
    
    # Send the message, mentioning the role if needed
    if ping_role:
        await channel.send(content=ping_role.mention, embed=embed)
    else:
        await channel.send(embed=embed)

def main():
    """Main entry point for the bot."""
    if not TOKEN:
        logger.error("No Discord token found in environment. Please set the DISCORD_TOKEN environment variable.")
        return
    
    try:    
        bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        logger.error("ERROR: Privileged intents are required but not enabled in the Discord Developer Portal.")
        logger.error("Please go to https://discord.com/developers/applications/ and enable the following intents:")
        logger.error("- MESSAGE CONTENT INTENT")
        logger.error("- SERVER MEMBERS INTENT")
        logger.error("For your bot in the 'Bot' section of your application.")

if __name__ == "__main__":
    main()
