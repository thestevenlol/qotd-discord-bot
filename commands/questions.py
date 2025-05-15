import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import os
import io

DB_PATH = os.getenv('DB_PATH', "qotd.db")

class Questions(commands.Cog):
    """Commands for managing questions."""
    
    def __init__(self, bot):
        self.bot = bot
        
    async def get_pack_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for pack names."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute(
                '''SELECT name FROM question_packs 
                WHERE guild_id = ? AND name LIKE ?
                ORDER BY name''',
                (interaction.guild_id, f"%{current}%")
            ) as cursor:
                packs = await cursor.fetchall()
                
        return [
            app_commands.Choice(name=pack['name'], value=pack['name'])
            for pack in packs[:25]  # Max 25 choices
        ]
        
    @app_commands.command(name="addquestion", description="Add a question to a pack")
    @app_commands.describe(
        pack_name="Name of the pack to add the question to",
        question="The question to add"
    )
    @app_commands.autocomplete(pack_name=get_pack_autocomplete)
    async def addquestion(
        self,
        interaction: discord.Interaction,
        pack_name: str,
        question: str
    ):
        """Add a question to a specific pack."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if pack exists
            async with db.execute(
                'SELECT pack_id FROM question_packs WHERE guild_id = ? AND name = ?',
                (interaction.guild_id, pack_name)
            ) as cursor:
                pack = await cursor.fetchone()
                
            if not pack:
                await interaction.response.send_message(
                    f"Question pack '{pack_name}' not found. Create it with `/createpack`",
                    ephemeral=True
                )
                return
                
            # Add question
            await db.execute(
                '''INSERT INTO questions (pack_id, content, created_by)
                VALUES (?, ?, ?)''',
                (pack['pack_id'], question, interaction.user.id)
            )
            await db.commit()
            await interaction.response.send_message(
            f"Added question to pack '{pack_name}':\n{question}",
            ephemeral=True
        )
        
    @app_commands.command(name="deletequestion", description="Delete a question from a pack")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        question_id="ID of the question to delete"
    )
    async def deletequestion(
        self,
        interaction: discord.Interaction,
        question_id: int
    ):
        """Delete a question by its ID."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if question exists and belongs to this guild
            async with db.execute(
                '''SELECT q.question_id, p.name 
                FROM questions q
                JOIN question_packs p ON q.pack_id = p.pack_id
                WHERE q.question_id = ? AND p.guild_id = ?''',
                (question_id, interaction.guild_id)
            ) as cursor:
                question = await cursor.fetchone()
                
            if not question:
                await interaction.response.send_message(
                    f"Question with ID {question_id} not found in this server.",
                    ephemeral=True
                )
                return
                
            # Delete question
            await db.execute(
                'DELETE FROM questions WHERE question_id = ?',
                (question_id,)
            )
            await db.commit()
            
        await interaction.response.send_message(
            f"Deleted question with ID {question_id} from pack '{question['name']}'",
            ephemeral=True
        )
        
    @app_commands.command(name="suggestquestion", description="Suggest a question to be added to a pack")
    @app_commands.describe(
        pack_name="Name of the pack to suggest a question for",
        question="The question to suggest"
    )
    @app_commands.autocomplete(pack_name=get_pack_autocomplete)
    async def suggestquestion(
        self,
        interaction: discord.Interaction,
        pack_name: str,
        question: str
    ):
        """Suggest a question to be added to a specific pack."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if pack exists
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
                
            # Add suggestion
            await db.execute(
                '''INSERT INTO suggestions (guild_id, pack_id, content, suggested_by)
                VALUES (?, ?, ?, ?)''',
                (interaction.guild_id, pack['pack_id'], question, interaction.user.id)
            )
            await db.commit()
            
            # Get suggestion ID
            async with db.execute(
                'SELECT last_insert_rowid() as id'
            ) as cursor:
                result = await cursor.fetchone()
                suggestion_id = result['id']
                
        await interaction.response.send_message(
            f"Suggestion #{suggestion_id} submitted for review:\n{question}\n\n"
            f"Staff members can review this with `/reviewsuggestion {suggestion_id}`",
            ephemeral=True
        )
        
        # Notify staff with manage_messages permission
        # For now, just log it - a more complex notification system could be added later
        for member in interaction.guild.members:
            if member.guild_permissions.manage_messages and not member.bot:
                try:
                    # Find a staff-only channel to notify
                    for channel in interaction.guild.text_channels:
                        if "staff" in channel.name.lower() or "mod" in channel.name.lower():
                            embed = discord.Embed(
                                title="New Question Suggestion",
                                description=f"Pack: {pack_name}\n"
                                            f"Question: {question}\n"
                                            f"Submitted by: {interaction.user.mention}",
                                color=discord.Color.blue()
                            )
                            embed.set_footer(text=f"Suggestion ID: {suggestion_id}")
                            
                            await channel.send(embed=embed)
                            break
                except:
                    pass
                    
    @app_commands.command(name="reviewsuggestion", description="Review a suggested question")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        suggestion_id="ID of the suggestion to review",
        action="Approve or reject the suggestion"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Approve", value="approve"),
        app_commands.Choice(name="Reject", value="reject")
    ])
    async def reviewsuggestion(
        self,
        interaction: discord.Interaction,
        suggestion_id: int,
        action: str
    ):
        """Review a question suggestion."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Check if suggestion exists and belongs to this guild
            async with db.execute(
                '''SELECT s.*, p.name as pack_name
                FROM suggestions s
                JOIN question_packs p ON s.pack_id = p.pack_id
                WHERE s.suggestion_id = ? AND s.guild_id = ?''',
                (suggestion_id, interaction.guild_id)
            ) as cursor:
                suggestion = await cursor.fetchone()
                
            if not suggestion:
                await interaction.response.send_message(
                    f"Suggestion with ID {suggestion_id} not found in this server.",
                    ephemeral=True
                )
                return
                
            if suggestion['status'] != 'pending':
                await interaction.response.send_message(
                    f"This suggestion has already been {suggestion['status']}.",
                    ephemeral=True
                )
                return
                
            if action == "approve":
                # Add the question
                await db.execute(
                    '''INSERT INTO questions (pack_id, content, created_by)
                    VALUES (?, ?, ?)''',
                    (suggestion['pack_id'], suggestion['content'], suggestion['suggested_by'])
                )
                
                # Update suggestion status
                await db.execute(
                    '''UPDATE suggestions 
                    SET status = 'approved', reviewed_by = ?
                    WHERE suggestion_id = ?''',
                    (interaction.user.id, suggestion_id)
                )
                
                await db.commit()
                
                await interaction.response.send_message(
                    f"Approved suggestion #{suggestion_id} and added to pack '{suggestion['pack_name']}':\n"
                    f"{suggestion['content']}",
                    ephemeral=True
                )
                
                # Try to notify the user who made the suggestion
                try:
                    suggester = await interaction.guild.fetch_member(suggestion['suggested_by'])
                    if suggester:
                        await suggester.send(
                            f"Your question suggestion for '{suggestion['pack_name']}' has been approved:\n"
                            f"{suggestion['content']}"
                        )
                except:
                    pass
            else:
                # Update suggestion status
                await db.execute(
                    '''UPDATE suggestions 
                    SET status = 'rejected', reviewed_by = ?
                    WHERE suggestion_id = ?''',
                    (interaction.user.id, suggestion_id)
                )
                await db.commit()
                
                await interaction.response.send_message(
                    f"Rejected suggestion #{suggestion_id} for pack '{suggestion['pack_name']}':\n"
                    f"{suggestion['content']}",
                    ephemeral=True
                )
                
    @app_commands.command(name="listsuggestions", description="List all pending question suggestions")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def listsuggestions(self, interaction: discord.Interaction):
        """List all pending question suggestions."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            async with db.execute(
                '''SELECT s.*, p.name as pack_name
                FROM suggestions s
                JOIN question_packs p ON s.pack_id = p.pack_id
                WHERE s.guild_id = ? AND s.status = 'pending'
                ORDER BY s.suggested_at''',
                (interaction.guild_id,)
            ) as cursor:
                suggestions = await cursor.fetchall()
                
        if not suggestions:
            await interaction.response.send_message(
                "No pending question suggestions found.",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Pending Question Suggestions",
            color=discord.Color.blue()
        )
        
        for suggestion in suggestions:
            embed.add_field(
                name=f"Suggestion #{suggestion['suggestion_id']} - Pack: {suggestion['pack_name']}",
                value=f"{suggestion['content']}\n"
                      f"Suggested by: <@{suggestion['suggested_by']}>\n"
                      f"To review: `/reviewsuggestion {suggestion['suggestion_id']} <approve/reject>`",
                inline=False
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="uploadquestions", description="Upload a text file with questions (one per line)")
    @app_commands.describe(
        pack_name="Name of the pack to add questions to",
        file="Text file with questions (one per line)"
    )
    @app_commands.autocomplete(pack_name=get_pack_autocomplete)
    async def uploadquestions(
        self,
        interaction: discord.Interaction,
        pack_name: str,
        file: discord.Attachment
    ):
        """Add multiple questions from a text file to a specific pack."""
        
        # Check if the file is a text file (or at least not too large)
        if file.size > 1_000_000:  # Limit to ~1MB
            await interaction.response.send_message(
                "File too large. Please upload a smaller file (under 1MB).",
                ephemeral=True
            )
            return
            
        # Defer reply since file processing might take time
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Download and read the file content
            file_bytes = await file.read()
            content = file_bytes.decode('utf-8')
            
            # Split by newlines and filter out empty lines
            question_list = [q.strip() for q in content.split('\n') if q.strip()]
            
            if not question_list:
                await interaction.followup.send(
                    "No valid questions found in the file. Make sure each question is on its own line.",
                    ephemeral=True
                )
                return
                
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                
                # Check if pack exists
                async with db.execute(
                    'SELECT pack_id FROM question_packs WHERE guild_id = ? AND name = ?',
                    (interaction.guild_id, pack_name)
                ) as cursor:
                    pack = await cursor.fetchone()
                    
                if not pack:
                    await interaction.followup.send(
                        f"Question pack '{pack_name}' not found. Create it with `/createpack`",
                        ephemeral=True
                    )
                    return
                    
                # Add questions
                for question in question_list:
                    await db.execute(
                        '''INSERT INTO questions (pack_id, content, created_by)
                        VALUES (?, ?, ?)''',
                        (pack['pack_id'], question, interaction.user.id)
                    )
                await db.commit()
                
            # Show preview of added questions
            preview_questions = question_list[:5]
            remaining = len(question_list) - len(preview_questions)
            
            preview_text = "\n".join([f"- {q}" for q in preview_questions])
            if remaining > 0:
                preview_text += f"\n... and {remaining} more"
                
            await interaction.followup.send(
                f"Added {len(question_list)} questions to pack '{pack_name}' from file `{file.filename}`\n\n"
                f"Preview:\n{preview_text}",
                ephemeral=True
            )
            
        except UnicodeDecodeError:
            await interaction.followup.send(
                "Could not decode the file. Please ensure it's a plain text file with UTF-8 encoding.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"An error occurred while processing the file: {str(e)}",
                ephemeral=True
            )
    
async def setup(bot):
    """Set up the questions commands cog."""
    await bot.add_cog(Questions(bot))
