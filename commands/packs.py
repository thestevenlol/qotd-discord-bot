import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
import os

DB_PATH = os.getenv('DB_PATH', "qotd.db")

class PaginationView(discord.ui.View):
    """Improved pagination view with faster page changes."""
    
    def __init__(self, embeds):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.current_page = 0
        self.total_pages = len(embeds)
        
        # Update button states initially
        self.update_button_states()
    
    def update_button_states(self):
        """Update the button states based on the current page."""
        # First button (previous) - disable if on first page
        self.prev_button.disabled = self.current_page == 0
        
        # Middle button (page indicator)
        self.page_indicator.label = f"Page {self.current_page + 1}/{self.total_pages}"
        
        # Last button (next) - disable if on last page
        self.next_button.disabled = self.current_page == self.total_pages - 1
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous page."""
        self.current_page = max(0, self.current_page - 1)
        self.update_button_states()
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page],
            view=self
        )
    
    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Page indicator (does nothing when clicked)."""
        await interaction.response.defer()
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next page."""
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_button_states()
        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page], 
            view=self
        )
    
    async def start(self, ctx):
        """Start the pagination."""
        await ctx.response.send_message(
            embed=self.embeds[0],
            view=self
        )


class Packs(commands.Cog):
    """Commands for managing question packs."""
    
    def __init__(self, bot):
        self.bot = bot
        
    @app_commands.command(name="createpack", description="Create a new question pack")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        name="Name of the question pack",
        description="Description for the question pack"
    )
    async def createpack(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = None
    ):
        """Create a new question pack."""
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute(
                    '''INSERT INTO question_packs (guild_id, name, description, created_by)
                    VALUES (?, ?, ?, ?)''',
                    (interaction.guild_id, name, description, interaction.user.id)
                )
                await db.commit()
                
                await interaction.response.send_message(
                    f"Created question pack: **{name}**\n"
                    f"Description: {description or 'None'}\n\n"
                    f"Add questions with `/addquestion` and link to channels with `/linkpack`",
                    ephemeral=True
                )
            except aiosqlite.IntegrityError:
                await interaction.response.send_message(
                    f"A question pack with name '{name}' already exists in this server.",
                    ephemeral=True
                )
                
    @app_commands.command(name="deletepack", description="Delete a question pack")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        name="Name of the question pack to delete",
        confirm="Type 'confirm' to delete the pack (this will delete all questions in the pack)"
    )
    async def deletepack(
        self,
        interaction: discord.Interaction,
        name: str,
        confirm: str
    ):
        """Delete a question pack and all its questions."""
        if confirm.lower() != "confirm":
            await interaction.response.send_message(
                "Pack deletion canceled. To confirm deletion, type 'confirm'.",
                ephemeral=True
            )
            return
            
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if pack exists
            async with db.execute(
                'SELECT pack_id FROM question_packs WHERE guild_id = ? AND name = ?',
                (interaction.guild_id, name)
            ) as cursor:
                pack = await cursor.fetchone()
                
            if not pack:
                await interaction.response.send_message(
                    f"Question pack '{name}' not found.",
                    ephemeral=True
                )
                return
                
            # Get count of questions
            async with db.execute(
                'SELECT COUNT(*) as count FROM questions WHERE pack_id = ?',
                (pack['pack_id'],)
            ) as cursor:
                result = await cursor.fetchone()
                question_count = result['count']
            
            # Delete from channel_packs
            await db.execute(
                'DELETE FROM channel_packs WHERE pack_id = ?',
                (pack['pack_id'],)
            )
            
            # Delete questions
            await db.execute(
                'DELETE FROM questions WHERE pack_id = ?',
                (pack['pack_id'],)
            )
            
            # Delete suggestions
            await db.execute(
                'DELETE FROM suggestions WHERE pack_id = ?',
                (pack['pack_id'],)
            )
            
            # Delete pack
            await db.execute(
                'DELETE FROM question_packs WHERE pack_id = ?',
                (pack['pack_id'],)
            )
            
            await db.commit()
            
        await interaction.response.send_message(
            f"Deleted question pack '{name}' and {question_count} questions.",
            ephemeral=True
        )
        
    @app_commands.command(name="listpacks", description="List all question packs in this server")
    async def listpacks(self, interaction: discord.Interaction):
        """List all question packs in this server."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute(
                '''SELECT p.*, 
                   (SELECT COUNT(*) FROM questions WHERE pack_id = p.pack_id) as question_count,
                   (SELECT COUNT(*) FROM channel_packs WHERE pack_id = p.pack_id) as channel_count
                FROM question_packs p
                WHERE guild_id = ?
                ORDER BY name''',
                (interaction.guild_id,)
            ) as cursor:
                packs = await cursor.fetchall()
                
        if not packs:
            await interaction.response.send_message(
                "No question packs found in this server. Create one with `/createpack`",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Question Packs",
            color=discord.Color.blue()
        )
        
        for pack in packs:
            embed.add_field(
                name=pack['name'],
                value=f"Description: {pack['description'] or 'None'}\n"
                      f"Questions: {pack['question_count']}\n"
                      f"Linked to {pack['channel_count']} channel(s)",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="viewpack", description="View all questions in a pack")
    @app_commands.describe(
        name="Name of the question pack to view"
    )
    async def viewpack(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        """View all questions in a specific pack."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if pack exists
            async with db.execute(
                'SELECT * FROM question_packs WHERE guild_id = ? AND name = ?',
                (interaction.guild_id, name)
            ) as cursor:
                pack = await cursor.fetchone()
                
            if not pack:
                await interaction.response.send_message(
                    f"Question pack '{name}' not found.",
                    ephemeral=True
                )
                return
                  # Get questions
            async with db.execute(
                '''SELECT * FROM questions 
                WHERE pack_id = ?
                ORDER BY times_sent ASC, last_sent ASC NULLS FIRST, question_id ASC''',
                (pack['pack_id'],)
            ) as cursor:
                questions = await cursor.fetchall()
                
        if not questions:
            await interaction.response.send_message(
                f"No questions found in pack '{name}'. Add questions with `/addquestion`",
                ephemeral=True
            )
            return        # Create embeds for pagination (10 questions per page)
        embeds = []
        for i in range(0, len(questions), 10):
            page_questions = questions[i:i+10]
            
            embed = discord.Embed(
                title=f"Question Pack: {name}",
                description=pack['description'] or "No description",
                color=discord.Color.blue()
            )
            
            for idx, question in enumerate(page_questions, start=i+1):
                sent_status = "Never sent"
                if question['last_sent']:
                    sent_status = f"Sent {question['times_sent']} time(s), last on {question['last_sent']}"
                    
                embed.add_field(
                    name=f"Question {idx}",
                    value=f"{question['content']}\n*{sent_status}*",
                    inline=False
                )
                
            embed.set_footer(text=f"Page {len(embeds) + 1}/{(len(questions) + 9) // 10}")
            embeds.append(embed)
              # Display paginated embeds
        paginator = PaginationView(embeds)
        await paginator.start(interaction)
            
            
async def setup(bot):
    """Set up the packs commands cog."""
    await bot.add_cog(Packs(bot))
