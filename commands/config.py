import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
from datetime import datetime, time
import os

DB_PATH = os.getenv('DB_PATH', "qotd.db")

class Config(commands.Cog):
    """Commands for configuring the Question of the Day bot."""
    
    def __init__(self, bot):
        self.bot = bot
        
    @app_commands.command(name="setup", description="Set up a channel for Question of the Day")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="The channel to send questions to",
        time="The time to send questions (24-hour format, HH:MM)",
        frequency="How often to send questions",
        ping_role="Role to ping when sending questions (optional)"
    )
    @app_commands.choices(frequency=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly - Monday", value="weekly-0"),
        app_commands.Choice(name="Weekly - Tuesday", value="weekly-1"),
        app_commands.Choice(name="Weekly - Wednesday", value="weekly-2"),
        app_commands.Choice(name="Weekly - Thursday", value="weekly-3"),
        app_commands.Choice(name="Weekly - Friday", value="weekly-4"),
        app_commands.Choice(name="Weekly - Saturday", value="weekly-5"),
        app_commands.Choice(name="Weekly - Sunday", value="weekly-6"),
    ])
    async def setup(
        self, 
        interaction: discord.Interaction, 
        channel: discord.TextChannel,
        time: str,
        frequency: str,
        ping_role: discord.Role = None
    ):
        """Set up a channel for receiving Question of the Day."""
        
        # Validate time format (HH:MM)
        try:
            hour, minute = map(int, time.split(':'))
            if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                raise ValueError("Invalid time range")
        except Exception:
            await interaction.response.send_message("Invalid time format. Please use 24-hour format (HH:MM)", ephemeral=True)
            return
            
        # Store configuration in database
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if channel already configured
            async with db.execute(
                'SELECT channel_id FROM channel_config WHERE channel_id = ?',
                (channel.id,)
            ) as cursor:
                existing = await cursor.fetchone()
                
            if existing:
                # Update existing config
                await db.execute(
                    '''UPDATE channel_config 
                    SET time = ?, frequency = ?, ping_role_id = ?
                    WHERE channel_id = ?''',
                    (time, frequency, ping_role.id if ping_role else None, channel.id)
                )
                message = "Updated"
            else:
                # Insert new config
                await db.execute(
                    '''INSERT INTO channel_config 
                    (channel_id, guild_id, time, frequency, ping_role_id)
                    VALUES (?, ?, ?, ?, ?)''',
                    (channel.id, interaction.guild_id, time, frequency, 
                     ping_role.id if ping_role else None)
                )
                message = "Set up"
                
            await db.commit()
        
        # Schedule the question
        from main import schedule_question
        config = {
            'channel_id': channel.id,
            'time': time,
            'frequency': frequency,
            'ping_role_id': ping_role.id if ping_role else None,
            'last_question_id': None
        }
        await schedule_question(config)
        
        await interaction.response.send_message(
            f"{message} Question of the Day for {channel.mention}\n"
            f"Time: {time}\n"
            f"Frequency: {frequency}\n"
            f"Ping Role: {ping_role.mention if ping_role else 'None'}\n\n"
            f"Note: You need to associate at least one question pack with this channel using `/linkpack`",
            ephemeral=True
        )
        
    @app_commands.command(name="linkpack", description="Link a question pack to a channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="The channel to link a pack to",
        pack_name="The name of the question pack to link"
    )
    async def linkpack(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        pack_name: str
    ):
        """Link a question pack to a specific channel."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if channel is configured
            async with db.execute(
                'SELECT channel_id FROM channel_config WHERE channel_id = ?',
                (channel.id,)
            ) as cursor:
                channel_config = await cursor.fetchone()
                
            if not channel_config:
                await interaction.response.send_message(
                    f"Channel {channel.mention} is not configured for Question of the Day. "
                    f"Use `/setup` first.",
                    ephemeral=True
                )
                return
                
            # Get pack ID
            async with db.execute(
                'SELECT pack_id FROM question_packs WHERE guild_id = ? AND name = ?',
                (interaction.guild_id, pack_name)
            ) as cursor:
                pack = await cursor.fetchone()
                
            if not pack:
                await interaction.response.send_message(
                    f"Question pack '{pack_name}' not found. "
                    f"Create it first with `/createpack`.",
                    ephemeral=True
                )
                return
                
            # Link pack to channel
            try:
                await db.execute(
                    'INSERT INTO channel_packs (channel_id, pack_id) VALUES (?, ?)',
                    (channel.id, pack['pack_id'])
                )
                await db.commit()
                
                await interaction.response.send_message(
                    f"Successfully linked question pack '{pack_name}' to {channel.mention}",
                    ephemeral=True
                )
            except aiosqlite.IntegrityError:
                await interaction.response.send_message(
                    f"This pack is already linked to {channel.mention}",
                    ephemeral=True
                )
                
    @app_commands.command(name="unlinkpack", description="Unlink a question pack from a channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="The channel to unlink a pack from",
        pack_name="The name of the question pack to unlink"
    )
    async def unlinkpack(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        pack_name: str
    ):
        """Unlink a question pack from a specific channel."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Get pack ID
            async with db.execute(
                'SELECT pack_id FROM question_packs WHERE guild_id = ? AND name = ?',
                (interaction.guild_id, pack_name)
            ) as cursor:
                pack = await cursor.fetchone()
                
            if not pack:
                await interaction.response.send_message(
                    f"Question pack '{pack_name}' not found.",
                    ephemeral=True
                )
                return
                
            # Unlink pack from channel
            await db.execute(
                'DELETE FROM channel_packs WHERE channel_id = ? AND pack_id = ?',
                (channel.id, pack['pack_id'])
            )
            await db.commit()
            
            # Check if any packs remain
            async with db.execute(
                'SELECT COUNT(*) as count FROM channel_packs WHERE channel_id = ?',
                (channel.id,)
            ) as cursor:
                result = await cursor.fetchone()
                
            await interaction.response.send_message(
                f"Unlinked question pack '{pack_name}' from {channel.mention}\n"
                f"{'Warning: This channel now has no question packs linked to it!' if result['count'] == 0 else ''}",
                ephemeral=True
            )
            
    @app_commands.command(name="listchannels", description="List all channels configured for Question of the Day")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def listchannels(self, interaction: discord.Interaction):
        """List all channels configured for Question of the Day in this server."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute(
                'SELECT * FROM channel_config WHERE guild_id = ?',
                (interaction.guild_id,)
            ) as cursor:
                channels = await cursor.fetchall()
                
        if not channels:
            await interaction.response.send_message(
                "No channels are configured for Question of the Day in this server.",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Question of the Day - Configured Channels",
            color=discord.Color.blue()
        )
        
        for config in channels:
            channel = interaction.guild.get_channel(config['channel_id'])
            if not channel:
                continue
                
            ping_role = "None"
            if config['ping_role_id']:
                role = interaction.guild.get_role(config['ping_role_id'])
                ping_role = role.mention if role else "Role not found"
                
            embed.add_field(
                name=f"#{channel.name}",
                value=f"Time: {config['time']}\n"
                      f"Frequency: {config['frequency']}\n"
                      f"Ping Role: {ping_role}",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @app_commands.command(name="sendnow", description="Send a question immediately to a channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        channel="The channel to send a question to"
    )
    async def sendnow(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Send a question immediately to a specified channel."""
        # Check if channel is configured
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                'SELECT channel_id FROM channel_config WHERE channel_id = ?',
                (channel.id,)
            ) as cursor:
                channel_config = await cursor.fetchone()
                
        if not channel_config:
            await interaction.response.send_message(
                f"Channel {channel.mention} is not configured for Question of the Day. "
                f"Use `/setup` first.",
                ephemeral=True
            )
            return
            
        # Defer response since sending might take some time
        await interaction.response.defer(ephemeral=True)
        
        # Import function from main
        from main import send_question_to_channel
        
        # Send the question
        await send_question_to_channel(channel)
        
        await interaction.followup.send(
            f"Successfully sent a question to {channel.mention}",
            ephemeral=True
        )

async def setup(bot):
    """Set up the config commands cog."""
    await bot.add_cog(Config(bot))
