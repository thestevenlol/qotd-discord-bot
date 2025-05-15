# Question of the Day Discord Bot

A Discord bot that automatically sends questions to designated channels at scheduled times. Perfect for community engagement, icebreakers, or daily discussions.

## Features

### Configuration
- Set up multiple channels for sending questions
- Schedule questions at specific times (e.g., 8PM daily)
- Configure frequency (daily, weekly on specific days)
- Assign ping roles for notifications
- Easy multi-channel setup

### Question Management
- Create custom question collections/packs
- Add questions individually or in bulk
- Suggestion system with staff approval workflow
- Interactive pack browser with pagination

### Other Features
- No question repetition until all questions have been used
- Send questions immediately with a command
- View all configured channels and question packs

## Commands

### Setup Commands
- `/setup` - Configure a channel for Question of the Day
- `/linkpack` - Link a question pack to a channel
- `/unlinkpack` - Remove a question pack from a channel
- `/listchannels` - List all configured channels
- `/sendnow` - Send a question immediately

### Pack Management
- `/createpack` - Create a new question pack
- `/deletepack` - Delete a question pack
- `/listpacks` - List all question packs
- `/viewpack` - View all questions in a pack with pagination

### Question Management
- `/addquestion` - Add a question to a pack
- `/uploadquestions` - Upload a text file with questions (one per line)
- `/deletequestion` - Delete a question
- `/suggestquestion` - Suggest a question (for users)
- `/reviewsuggestion` - Review a question suggestion (staff only)
- `/listsuggestions` - List pending suggestions (staff only)

## Setup

### Option 1: Standard Setup

1. Clone this repository
2. Create a Discord bot at https://discord.com/developers/applications/
   - Enable the following privileged intents in the Bot section:
     - Message Content Intent
     - Server Members Intent
   - Copy your bot token for the next step
3. Create a `.env` file with your Discord bot token:
   ```
   DISCORD_TOKEN=your_discord_token_here
   ```
4. Install dependencies (choose one method):
   ```
   # Using uv
   uv add discord.py python-dotenv apscheduler aiosqlite
   
   # OR using pip with requirements.txt
   pip install -r requirements.txt
   ```
5. Run the bot:
   ```
   # Using uv
   uv run main.py
   
   # OR using standard python
   python main.py
   ```

### Option 2: Docker Setup

1. Clone this repository
2. Create a Discord bot at https://discord.com/developers/applications/
   - Enable the privileged intents as described above
   - Copy your bot token for the next step
3. Create a `.env` file with your Discord bot token:
   ```
   DISCORD_TOKEN=your_discord_token_here
   ```
4. Create a data directory for persistent storage:
   ```
   mkdir data
   ```
5. Build and run with Docker Compose:
   ```
   docker-compose up -d
   ```
   
To view logs:
```
docker-compose logs -f
```

To stop the bot:
```
docker-compose down
```

## Permissions

This bot requires the following permissions:
- Read/Send Messages
- Embed Links
- Mention @everyone, @here, and All Roles
- Use Application Commands

## Database Schema

The bot uses SQLite for storage with the following structure:
- `channel_config`: Stores channel settings
- `question_packs`: Stores question collections
- `questions`: Stores individual questions
- `suggestions`: Stores suggested questions
- `channel_packs`: Links channels to question packs