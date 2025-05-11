# question_bot/cogs/questions_cog.py
import discord
from discord.ext import commands
from discord import app_commands, ui
from typing import List, Optional
import os # Import os

# from .. import db_manager, config # REMOVE config
from ..qotd_bot import db_manager

# Get STAFF_ROLE_NAME from environment variables
STAFF_ROLE_NAME_FROM_ENV = os.getenv("STAFF_ROLE_NAME", "Staff") # Default to "Staff"

# Helper to check if user has manage_guild permission or a specific staff role
def is_staff_member():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_guild:
            return True
        # Check for staff role by name (could also be by ID)
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME_FROM_ENV) # Use the env var
        if staff_role and staff_role in interaction.user.roles:
            return True
        
        await interaction.response.send_message("You don't have permission to use this command (Manage Server or Staff role required).", ephemeral=True)
        return False
    return commands.check(is_staff_member) # Pass the function itself


class QuestionPackView(discord.ui.View):
    def __init__(self, guild_id: int, pack_id: int, questions_with_status: list, items_per_page=5):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.pack_id = pack_id
        self.questions_with_status = questions_with_status # List of tuples (question_row, is_sent)
        self.items_per_page = items_per_page
        self.current_page = 0
        self.total_pages = (len(self.questions_with_status) - 1) // self.items_per_page + 1
        self._update_buttons()

    def _get_page_content(self) -> discord.Embed:
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page
        page_questions = self.questions_with_status[start_index:end_index]

        pack_info = db_manager.get_pack_by_id(self.pack_id)
        pack_name = pack_info['pack_name'] if pack_info else "Unknown Pack"

        embed = discord.Embed(
            title=f"Questions in Pack: {pack_name} (Page {self.current_page + 1}/{self.total_pages})",
            color=discord.Color.green()
        )
        if not page_questions:
            embed.description = "No questions on this page."
        else:
            description = ""
            for q_row, is_sent in page_questions:
                status_emoji = "✅ (Sent)" if is_sent else "◻️ (Unsent)"
                description += f"**ID: {q_row['question_id']}** {status_emoji}\n{q_row['question_text']}\n\n"
            embed.description = description
        return embed

    def _update_buttons(self):
        self.children[0].disabled = self.current_page == 0 # Previous button
        self.children[1].disabled = self.current_page >= self.total_pages - 1 # Next button
    
    async def show_page(self, interaction: discord.Interaction):
        embed = self._get_page_content()
        self._update_buttons()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.blurple, emoji="⬅️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.show_page(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.blurple, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await self.show_page(interaction)


class AddMultipleQuestionsModal(ui.Modal, title='Add Multiple Questions'):
    questions_input = ui.TextInput(
        label='Questions (one per line)',
        style=discord.TextStyle.paragraph,
        placeholder='What is your favorite color?\nWhat is your dream vacation?\n...',
        max_length=3000 # Discord limit for modals
    )

    def __init__(self, pack_id: int):
        super().__init__()
        self.pack_id = pack_id

    async def on_submit(self, interaction: discord.Interaction):
        questions = self.questions_input.value.splitlines()
        added_count = 0
        skipped_count = 0
        for q_text in questions:
            q_text = q_text.strip()
            if q_text: # Ignore empty lines
                db_manager.add_question_to_pack(self.pack_id, q_text)
                added_count += 1
            else:
                skipped_count +=1
        
        pack_info = db_manager.get_pack_by_id(self.pack_id)
        pack_name = pack_info['pack_name'] if pack_info else "Unknown Pack"
        await interaction.response.send_message(
            f"Added {added_count} questions to pack '{pack_name}'. Skipped {skipped_count} empty lines.",
            ephemeral=True
        )

class SuggestionReviewView(discord.ui.View):
    def __init__(self, suggestion_id: int, pack_choices: List[app_commands.Choice[str]]):
        super().__init__(timeout=None) # Persistent view
        self.suggestion_id = suggestion_id
        self.pack_select = discord.ui.Select(
            placeholder="Choose a pack to add to...",
            options=[discord.SelectOption(label=choice.name, value=str(choice.value)) for choice in pack_choices], # value must be str
            custom_id=f"suggestion_pack_select_{suggestion_id}"
        )
        self.add_item(self.pack_select)
        # Buttons need to be added after the select
        approve_button = discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"approve_suggestion_{suggestion_id}")
        deny_button = discord.ui.Button(label="Deny", style=discord.ButtonStyle.danger, custom_id=f"deny_suggestion_{suggestion_id}")
        self.add_item(approve_button)
        self.add_item(deny_button)


class QuestionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Need to register persistent views if any, but the suggestion review buttons will be handled via on_interaction
        # self.bot.add_view(SuggestionReviewView(suggestion_id=-1, pack_choices=[])) # Dummy for type hinting if needed elsewhere
        # However, the button callbacks are better handled in on_interaction or by making buttons subclasses of ui.Button

    pack_group = app_commands.Group(name="pack", description="Manage question packs.")

    @pack_group.command(name="create", description="Create a new question pack.")
    @app_commands.describe(name="The name for the new pack.")
    @is_staff_member()
    async def create_pack_cmd(self, interaction: discord.Interaction, name: str):
        if db_manager.create_pack(interaction.guild.id, name):
            await interaction.response.send_message(f"Question pack '{name}' created successfully.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Question pack '{name}' already exists in this server.", ephemeral=True)

    @pack_group.command(name="delete", description="Delete a question pack and all its questions.")
    @app_commands.describe(name="The name of the pack to delete.")
    @is_staff_member()
    async def delete_pack_cmd(self, interaction: discord.Interaction, name: str):
        if db_manager.delete_pack(interaction.guild.id, name):
            await interaction.response.send_message(f"Question pack '{name}' and all its questions deleted.", ephemeral=True)
            # If this was the active pack, clear it from config
            config = db_manager.get_guild_config(interaction.guild.id)
            if config and config['current_pack_name'] == name:
                db_manager.update_guild_config(interaction.guild.id, current_pack_name=None)
                await interaction.followup.send(f"Note: '{name}' was the active pack and has been unselected.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Question pack '{name}' not found.", ephemeral=True)
    
    @delete_pack_cmd.autocomplete('name')
    async def delete_pack_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        packs = db_manager.get_guild_packs(interaction.guild.id)
        return [
            app_commands.Choice(name=pack['pack_name'], value=pack['pack_name'])
            for pack in packs if current.lower() in pack['pack_name'].lower()
        ][:25]


    @pack_group.command(name="add", description="Add a single question to a pack.")
    @app_commands.describe(pack_name="The pack to add the question to.", question="The question text.")
    @is_staff_member()
    async def add_question_cmd(self, interaction: discord.Interaction, pack_name: str, question: str):
        pack = db_manager.get_pack(interaction.guild.id, pack_name)
        if not pack:
            await interaction.response.send_message(f"Pack '{pack_name}' not found.", ephemeral=True)
            return
        
        q_id = db_manager.add_question_to_pack(pack['pack_id'], question)
        await interaction.response.send_message(f"Question added to '{pack_name}' with ID {q_id}.", ephemeral=True)

    @add_question_cmd.autocomplete('pack_name')
    async def add_question_pack_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        packs = db_manager.get_guild_packs(interaction.guild.id)
        return [
            app_commands.Choice(name=pack['pack_name'], value=pack['pack_name'])
            for pack in packs if current.lower() in pack['pack_name'].lower()
        ][:25]

    @pack_group.command(name="addmultiple", description="Add multiple questions to a pack using a pop-up.")
    @app_commands.describe(pack_name="The pack to add questions to.")
    @is_staff_member()
    async def add_multiple_questions_cmd(self, interaction: discord.Interaction, pack_name: str):
        pack = db_manager.get_pack(interaction.guild.id, pack_name)
        if not pack:
            await interaction.response.send_message(f"Pack '{pack_name}' not found.", ephemeral=True)
            return
        modal = AddMultipleQuestionsModal(pack['pack_id'])
        await interaction.response.send_modal(modal)
        
    @add_multiple_questions_cmd.autocomplete('pack_name')
    async def add_multiple_pack_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        packs = db_manager.get_guild_packs(interaction.guild.id)
        return [
            app_commands.Choice(name=pack['pack_name'], value=pack['pack_name'])
            for pack in packs if current.lower() in pack['pack_name'].lower()
        ][:25]


    @pack_group.command(name="list", description="List all questions in a pack with sent status.")
    @app_commands.describe(pack_name="The name of the pack to list.")
    async def list_pack_cmd(self, interaction: discord.Interaction, pack_name: str):
        pack = db_manager.get_pack(interaction.guild.id, pack_name)
        if not pack:
            await interaction.response.send_message(f"Pack '{pack_name}' not found.", ephemeral=True)
            return

        all_questions = db_manager.get_questions_for_pack(pack['pack_id'])
        sent_question_ids = db_manager.get_sent_question_ids(interaction.guild.id, pack['pack_id'])
        
        questions_with_status = []
        unsent_questions = []
        sent_questions_list = []

        for q_row in all_questions:
            is_sent = q_row['question_id'] in sent_question_ids
            if is_sent:
                sent_questions_list.append((q_row, True))
            else:
                unsent_questions.append((q_row, False))
        
        # Show unsent first, then sent
        sorted_questions_with_status = unsent_questions + sent_questions_list

        if not sorted_questions_with_status:
            await interaction.response.send_message(f"Pack '{pack_name}' is empty.", ephemeral=True)
            return

        view = QuestionPackView(interaction.guild.id, pack['pack_id'], sorted_questions_with_status)
        embed = view._get_page_content() # Get initial embed
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @list_pack_cmd.autocomplete('pack_name')
    async def list_pack_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        packs = db_manager.get_guild_packs(interaction.guild.id)
        return [
            app_commands.Choice(name=pack['pack_name'], value=pack['pack_name'])
            for pack in packs if current.lower() in pack['pack_name'].lower()
        ][:25]


    question_group = app_commands.Group(name="question", description="Manage individual questions and suggestions.")

    @question_group.command(name="suggest", description="Suggest a new question for staff review.")
    @app_commands.describe(question_text="The question you want to suggest.")
    async def suggest_question_cmd(self, interaction: discord.Interaction, question_text: str):
        suggestion_id = db_manager.add_suggestion(interaction.guild.id, interaction.user.id, question_text)
        await interaction.response.send_message(
            f"Thank you! Your question suggestion has been submitted with ID {suggestion_id} for staff review.",
            ephemeral=True
        )
        # Optionally, notify staff in a specific channel
        # staff_channel_id = ...
        # staff_channel = self.bot.get_channel(staff_channel_id)
        # if staff_channel:
        #     await staff_channel.send(f"New question suggestion from {interaction.user.mention}: \"{question_text}\" (ID: {suggestion_id})")


    @question_group.command(name="review", description="Staff: Review pending question suggestions.")
    @is_staff_member()
    async def review_suggestions_cmd(self, interaction: discord.Interaction):
        suggestions = db_manager.get_pending_suggestions(interaction.guild.id)
        if not suggestions:
            await interaction.response.send_message("No pending question suggestions.", ephemeral=True)
            return

        guild_packs = db_manager.get_guild_packs(interaction.guild.id)
        pack_choices = [
            app_commands.Choice(name=pack['pack_name'], value=str(pack['pack_id'])) # Store pack_id as string for select
            for pack in guild_packs
        ]

        if not pack_choices:
             await interaction.response.send_message(
                "No question packs exist in this server. Please create a pack before approving suggestions.",
                ephemeral=True
            )
             return

        await interaction.response.send_message("Pending suggestions:", ephemeral=True) # Initial response

        for suggestion in suggestions[:5]: # Show first 5 to avoid spam, can add pagination later
            sug_user = interaction.guild.get_member(suggestion['user_id']) or f"User ID: {suggestion['user_id']}"
            embed = discord.Embed(
                title=f"Suggestion ID: {suggestion['suggestion_id']}",
                description=f"**Suggested by:** {sug_user}\n**Question:** {suggestion['question_text']}",
                color=discord.Color.orange()
            )
            view = SuggestionReviewView(suggestion['suggestion_id'], pack_choices)
            # Send as followup because initial response was made
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")
        if not custom_id:
            return

        if custom_id.startswith("approve_suggestion_") or custom_id.startswith("deny_suggestion_"):
            # Manually check staff status here as it's not a command
            is_staff_user = interaction.user.guild_permissions.manage_guild or \
                            (discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME_FROM_ENV) in interaction.user.roles if interaction.user.roles else False)

            if not is_staff_user:
                await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)
                return
            
            suggestion_id = int(custom_id.split("_")[-1])
            suggestion = db_manager.get_suggestion(suggestion_id)

            if not suggestion or suggestion['status'] != 'pending':
                await interaction.response.edit_message(content="This suggestion has already been processed or does not exist.", view=None, embed=None)
                return

            if custom_id.startswith("approve_suggestion_"):
                # (The logic for finding selected_pack_id_str remains the same)
                selected_pack_id_str = None
                if interaction.message and interaction.message.components:
                    for action_row_component in interaction.message.components:
                        if not hasattr(action_row_component, 'children'): continue
                        for component in action_row_component.children:
                            if isinstance(component, discord.ui.Select) and component.custom_id == f"suggestion_pack_select_{suggestion_id}":
                                if component.values:
                                    selected_pack_id_str = component.values[0]
                                break
                        if selected_pack_id_str: break
                
                if not selected_pack_id_str:
                    await interaction.response.send_message(
                        "Please select a pack from the dropdown menu first, then click 'Approve' again.",
                        ephemeral=True
                    )
                    return

                pack_id = int(selected_pack_id_str)
                db_manager.add_question_to_pack(pack_id, suggestion['question_text'])
                db_manager.update_suggestion_status(suggestion_id, 'approved')
                pack_info = db_manager.get_pack_by_id(pack_id)
                pack_name = pack_info['pack_name'] if pack_info else "Selected Pack"
                
                await interaction.response.edit_message(
                    content=f"Suggestion ID {suggestion_id} ('{suggestion['question_text'][:50]}...') approved and added to pack '{pack_name}'.",
                    view=None, embed=None
                )

            elif custom_id.startswith("deny_suggestion_"):
                db_manager.update_suggestion_status(suggestion_id, 'denied')
                await interaction.response.edit_message(
                    content=f"Suggestion ID {suggestion_id} denied.",
                    view=None, embed=None
                )
        
        elif custom_id.startswith("suggestion_pack_select_"):
            await interaction.response.defer()


async def setup(bot):
    await bot.add_cog(QuestionsCog(bot))