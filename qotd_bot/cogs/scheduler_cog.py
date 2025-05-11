# question_bot/cogs/scheduler_cog.py
import discord
from discord.ext import commands, tasks
import datetime
import asyncio
import random
from ..qotd_bot import db_manager # Relative import

class SchedulerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.question_sender.start()

    def cog_unload(self):
        self.question_sender.cancel()

    @tasks.loop(minutes=1) # Check every minute
    async def question_sender(self):
        await self.bot.wait_until_ready() # Ensure bot is fully ready
        
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_time_str = now_utc.strftime("%H:%M")
        current_day_of_week = now_utc.weekday() # Monday is 0 and Sunday is 6

        configs = db_manager.get_all_guild_configs()
        
        for config_row in configs:
            guild_id = config_row['guild_id']
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"Scheduler: Guild {guild_id} not found. Skipping.")
                continue

            if config_row['send_time'] != current_time_str:
                continue # Not the right time

            if config_row['frequency'] == 'weekly' and current_day_of_week != 0: # Send weekly on Mondays (0)
                # You can make the day configurable too, e.g. store 'weekly_0', 'weekly_1' etc.
                continue 
            
            if config_row['frequency'] == 'disabled':
                continue

            target_channel_id = config_row['channel_id']
            channel = guild.get_channel(target_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                print(f"Scheduler: Channel {target_channel_id} not found or not text channel in guild {guild_id}. Skipping.")
                continue

            pack_name = config_row['current_pack_name']
            if not pack_name:
                print(f"Scheduler: No active pack for guild {guild_id}. Skipping.")
                # await channel.send("Warning: No question pack is currently selected. Please configure one using `/config pack`.")
                continue
            
            pack = db_manager.get_pack(guild_id, pack_name)
            if not pack:
                print(f"Scheduler: Active pack '{pack_name}' not found for guild {guild_id}. Skipping.")
                # await channel.send(f"Warning: The active question pack '{pack_name}' could not be found. Please reconfigure.")
                continue
            
            pack_id = pack['pack_id']
            question_to_send = db_manager.get_unsent_question(guild_id, pack_id)

            if not question_to_send:
                # All questions in this pack have been sent for this guild.
                # Option 1: Notify and stop for this pack.
                # Option 2: Reset sent questions and pick one. (Looping)
                # For now, let's notify and stop.
                msg = f"All questions from the pack '{pack_name}' have been sent! Consider adding more questions or switching packs."
                # Option to reset:
                # db_manager.reset_sent_questions_for_pack(guild_id, pack_id)
                # question_to_send = db_manager.get_unsent_question(guild_id, pack_id)
                # if not question_to_send: # Still no question after reset (empty pack)
                #     msg = f"The pack '{pack_name}' is empty or something went wrong after reset."
                # else:
                #    msg = None # Will proceed to send
                if msg: # Only send notification if no question found even after potential reset
                    try:
                        await channel.send(msg)
                    except discord.Forbidden:
                        print(f"Scheduler: Missing permissions to send message in {channel.name} ({guild.name})")
                    except Exception as e:
                        print(f"Scheduler: Error sending 'all sent' notification: {e}")
                continue # Move to next guild config

            # Prepare message
            content = ""
            ping_role_id = config_row['ping_role_id']
            if ping_role_id:
                role = guild.get_role(ping_role_id)
                if role:
                    content += f"{role.mention} "
            
            embed = discord.Embed(
                title="❓ Question of the Day!" if config_row['frequency'] == 'daily' else "❓ Question of the Week!",
                description=question_to_send['question_text'],
                color=discord.Color.random() # Fun random color
            )
            embed.set_footer(text=f"From pack: {pack_name}")

            try:
                await channel.send(content=content if content else None, embed=embed)
                db_manager.mark_question_as_sent(guild_id, pack_id, question_to_send['question_id'])
                print(f"Scheduler: Sent question {question_to_send['question_id']} to guild {guild_id} channel {target_channel_id}")
            except discord.Forbidden:
                print(f"Scheduler: Missing permissions to send message in {channel.name} ({guild.name}) for question {question_to_send['question_id']}")
            except Exception as e:
                print(f"Scheduler: Error sending question {question_to_send['question_id']}: {e}")
            
            await asyncio.sleep(1) # Small delay to avoid hitting rate limits if many guilds at same time

async def setup(bot):
    await bot.add_cog(SchedulerCog(bot))