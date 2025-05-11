# question_bot/cogs/config_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import re # For time validation
from ..qotd_bot import db_manager # Use .. to go up one level for imports

# Helper to check if user has manage_guild permission
def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        await interaction.response.send_message("You don't have permission to use this command (Manage Server required).", ephemeral=True)
        return False
    return commands.check(predicate)


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    config_group = app_commands.Group(name="config", description="Configure question sending settings for this server.")

    @config_group.command(name="channel", description="Set the channel where questions will be sent.")
    @app_commands.describe(channel="The channel to send questions to.")
    @is_staff()
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        db_manager.update_guild_config(interaction.guild.id, channel_id=channel.id)
        await interaction.response.send_message(f"Questions will now be sent to {channel.mention}.", ephemeral=True)

    @config_group.command(name="time", description="Set the time to send questions (HH:MM in UTC).")
    @app_commands.describe(time_str="Time in HH:MM format (e.g., 08:00 or 20:00). Assumed UTC.")
    @is_staff()
    async def set_time(self, interaction: discord.Interaction, time_str: str):
        if not re.match(r"^(0[0-9]|1[0-9]|2[0-3]):([0-5][0-9])$", time_str):
            await interaction.response.send_message("Invalid time format. Please use HH:MM (e.g., 08:00 or 20:00).", ephemeral=True)
            return
        db_manager.update_guild_config(interaction.guild.id, send_time=time_str)
        await interaction.response.send_message(f"Questions will now be sent at {time_str} UTC.", ephemeral=True)

    @config_group.command(name="frequency", description="Set how often to send questions.")
    @app_commands.describe(frequency="How often to send (daily, weekly, or disabled).")
    @app_commands.choices(frequency=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
        app_commands.Choice(name="Disabled", value="disabled")
    ])
    @is_staff()
    async def set_frequency(self, interaction: discord.Interaction, frequency: app_commands.Choice[str]):
        db_manager.update_guild_config(interaction.guild.id, frequency=frequency.value)
        await interaction.response.send_message(f"Question frequency set to: {frequency.name}.", ephemeral=True)

    @config_group.command(name="pingrole", description="Set a role to ping when a question is sent.")
    @app_commands.describe(role="The role to ping (optional, type 'none' to remove).")
    @is_staff()
    async def set_pingrole(self, interaction: discord.Interaction, role: str):
        ping_role_id = None
        message = "Ping role removed."
        if role.lower() != 'none':
            try:
                resolved_role = await commands.RoleConverter().convert(interaction, role)
                ping_role_id = resolved_role.id
                message = f"Ping role set to {resolved_role.mention}."
            except commands.RoleNotFound:
                await interaction.response.send_message(f"Role '{role}' not found. Type 'none' to remove the ping role.", ephemeral=True)
                return
        
        db_manager.update_guild_config(interaction.guild.id, ping_role_id=ping_role_id)
        await interaction.response.send_message(message, ephemeral=True)

    @config_group.command(name="pack", description="Select the active question pack for this server.")
    @app_commands.describe(pack_name="The name of the question pack to use.")
    @is_staff()
    async def set_pack(self, interaction: discord.Interaction, pack_name: str):
        pack = db_manager.get_pack(interaction.guild.id, pack_name)
        if not pack:
            await interaction.response.send_message(f"Pack '{pack_name}' not found. Create it first or check spelling.", ephemeral=True)
            return
        db_manager.update_guild_config(interaction.guild.id, current_pack_name=pack_name)
        await interaction.response.send_message(f"Active question pack set to: {pack_name}.", ephemeral=True)
        
    # Autocomplete for pack_name
    @set_pack.autocomplete('pack_name')
    async def pack_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        packs = db_manager.get_guild_packs(interaction.guild.id)
        return [
            app_commands.Choice(name=pack['pack_name'], value=pack['pack_name'])
            for pack in packs if current.lower() in pack['pack_name'].lower()
        ][:25]


    @config_group.command(name="view", description="View the current configuration for this server.")
    async def view_config(self, interaction: discord.Interaction):
        config = db_manager.get_guild_config(interaction.guild.id)
        if not config:
            await interaction.response.send_message("No configuration set for this server yet.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Question Bot Configuration for {interaction.guild.name}", color=discord.Color.blue())
        
        channel = self.bot.get_channel(config['channel_id']) if config['channel_id'] else "Not set"
        embed.add_field(name="Target Channel", value=channel.mention if isinstance(channel, discord.TextChannel) else channel, inline=False)
        
        embed.add_field(name="Send Time (UTC)", value=config['send_time'] or "Not set", inline=False)
        embed.add_field(name="Frequency", value=config['frequency'] or "Not set", inline=False)
        
        ping_role = interaction.guild.get_role(config['ping_role_id']) if config['ping_role_id'] else "Not set"
        embed.add_field(name="Ping Role", value=ping_role.mention if isinstance(ping_role, discord.Role) else ping_role, inline=False)
        
        embed.add_field(name="Active Pack", value=config['current_pack_name'] or "Not set", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ConfigCog(bot))