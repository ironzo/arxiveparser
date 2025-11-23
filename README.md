# arXiv Research Assistant Bot 🤖

An interactive Telegram bot that searches arXiv for research papers, generates summaries, and delivers comprehensive research digests directly to your Telegram.

## Features ✨

- 🔍 **Intelligent Search**: Uses LLM to generate optimized arXiv search queries
- 📄 **Paper Parsing**: Extracts and parses full paper content from arXiv
- 🤖 **AI Summaries**: Generates section-by-section and general paper summaries
- 📊 **Research Digest**: Creates a comprehensive digest of all relevant papers
- 💬 **Interactive Bot**: Conversational interface via Telegram
- 🔄 **Continuous Running**: Always available, handles multiple users
- 📚 **Deduplication**: Tracks processed papers to avoid redundant work
- 🔐 **Access Control**: Restrict bot to specific Telegram user IDs

## Setup 🛠️

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the `parser/` directory:

```env
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
UID=your_default_user_id_here

# Admin User ID (user with admin privileges to manage other users)
ADMIN_USER_ID=123456789

# Bot Access Control (comma-separated list of allowed Telegram user IDs)
# Leave empty to allow everyone, or specify user IDs to restrict access
ALLOWED_USER_IDS=123456789,987654321

# AI Model Configuration (for Gemini, optional)
API_KEY=your_gemini_api_key_here
```

**To get a Telegram Bot Token:**
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the instructions
3. Copy the token provided

**To get your User ID:**
1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Start a chat and it will show your user ID

**To Restrict Bot Access (Recommended):**
1. Get the Telegram user IDs of all authorized users (using @userinfobot)
2. Add them to `ALLOWED_USER_IDS` in `.env` as a comma-separated list
3. Example: `ALLOWED_USER_IDS=123456789,987654321,555666777`
4. Leave empty or omit to allow anyone to use the bot (not recommended for production)

### 3. Configure AI Model

Edit `parser/settings.py` to choose your model:

```python
# For Gemini (requires API_KEY in .env)
model_name = 'gemini-2.0-flash-001'

# OR for local Ollama (requires Ollama running)
model_name = "llama3.1:latest"
```

### 4. Install Ollama (Optional, for local LLM)

If using local models:
```bash
# Install Ollama from https://ollama.ai
# Then pull your desired model:
ollama pull llama3.1:latest
```

## Usage 🚀

### Running the Bot

```bash
cd parser
python telegram_bot.py
```

The bot will start and display:
```
🤖 Bot is starting...
👉 Send /start to your bot to begin!
```

### Interacting with the Bot

1. **Start a Search**: Send `/start` to your bot in Telegram
2. **Enter Topic**: Type your research topic (e.g., "RAG", "Transformer models")
3. **Enter Start Date**: Provide the start date in format: `YYYY.MM.DD`
   - Example: `2024.10.20` (October 20, 2024)
4. **Enter End Date**: Provide the end date in format: `YYYY.MM.DD`
   - Example: `2024.10.24` (October 24, 2024)
5. **Wait for Results**: The bot will process papers and send you a digest
6. **Repeat**: Send `/start` anytime for a new search

**Date Format Features:**
- Simple, readable format: `YYYY.MM.DD`
- Automatic validation with helpful error messages
- Checks that end date is after start date
- Automatically converts to arXiv format (midnight to end-of-day)

### Available Commands

**User Commands:**
- `/start` - Begin a new research search
- `/cancel` - Cancel current search setup
- `/help` - Show help message

**Admin Commands** (only available to user with `ADMIN_USER_ID`):
- `/add_user` - Add a new authorized user
- `/remove_user` - Remove an authorized user
- `/list_users` - List all authorized users

### Example Conversation

```
You: /start

Bot: 👋 Welcome to arXiv Research Assistant!
     What research topic are you interested in?

You: RAG

Bot: ✅ Topic received: RAG
     📅 Now let's set the date range.
     📆 Enter the START date in format: YYYY.MM.DD
     
You: 2025.08.01

Bot: ✅ Start date received: 2025.08.01
     📆 Now enter the END date in format: YYYY.MM.DD

You: 2025.08.02

Bot: 🚀 Starting research process!
     📌 Topic: RAG
     📅 Date Range: 2025.08.01 to 2025.08.02
     🔍 Searching: [202508010000+TO+202508022359]
     ⏳ This may take a few minutes...

[Bot processes papers and sends digest...]

Bot: ✅ Research complete!
     Send /start to begin a new search!
```

**Date Validation Examples:**

Invalid format:
```
You: 2025/08/01
Bot: ❌ Invalid date format! Please use: YYYY.MM.DD
```

Invalid date range:
```
You: (start) 2025.08.05
     (end) 2025.08.01
Bot: ❌ Invalid date range! End date cannot be before start date.
```

## How It Works 🔄

1. **Query Construction**: LLM generates an optimized arXiv search query from your topic
2. **Paper Discovery**: Searches arXiv API for matching papers in the time range
3. **Content Extraction**: Fetches and parses full paper text from arXiv HTML
4. **Section Summaries**: Generates AI summaries for each paper section
5. **General Summary**: Creates a comprehensive summary of each paper
6. **Digest Generation**: Synthesizes all papers into a cohesive research digest
7. **Telegram Delivery**: Sends the digest with clickable paper links

## File Structure 📁

```
parser/
├── telegram_bot.py          # Interactive bot interface (NEW!)
├── main.py                  # Core processing pipeline
├── feed_parser.py           # arXiv API integration
├── text_parser.py           # Paper content extraction
├── summaries.py             # AI summary generation
├── telegram_notify.py       # Telegram messaging utilities
├── llm.py                   # LLM integration
├── prompt_library.py        # AI prompts
├── date_parser.py           # Date parsing utilities
├── settings.py              # Configuration
└── papers.json              # Paper database
```

## Running Standalone (Without Bot)

To run a one-time search without the bot:

```bash
cd parser
python main.py
```

Edit the hardcoded values in `main.py`:
```python
user_prompt = "RAG"  # Your research topic
time_range = "[202508010000+TO+202508020000]"  # Date range
```

## Troubleshooting 🔧

### Bot doesn't respond
- Check that `TELEGRAM_BOT_TOKEN` is correct in `.env`
- Verify the bot is running: `python telegram_bot.py`
- Check the console for error messages

### LLM errors
- For Gemini: Verify `API_KEY` is set and valid
- For Ollama: Ensure Ollama is running: `ollama serve`
- Check that the model specified in `settings.py` is available

### ArXiv API errors
- The bot automatically retries with a fallback query if the LLM-generated query fails
- Check your internet connection
- ArXiv API may have rate limits

### Paper parsing fails
- Some papers may not have HTML versions available
- The bot will use the abstract as a fallback

## Security 🔐

### Access Control

By default, the bot can be restricted to specific Telegram users:

**Configuration:**
```env
# In .env file
ADMIN_USER_ID=123456789
ALLOWED_USER_IDS=123456789,987654321,555666777
```

**Behavior:**
- If `ALLOWED_USER_IDS` is set: Only listed users can use the bot
- If `ALLOWED_USER_IDS` is empty/not set: Anyone can use the bot (⚠️ not recommended)

**What happens when unauthorized user tries:**
```
Unauthorized User: /start

Bot: 🚫 Access Denied
     Sorry, you are not authorized to use this bot.
     Your user ID: 999888777
     Please contact the bot administrator.
```

**Logs:**
- Authorized access: `INFO: Authorized user started session: 123456789 (@username)`
- Unauthorized attempts: `WARNING: Unauthorized access attempt by user_id: 999888777`

**How to find User IDs:**
1. Send message to [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID
3. Add that ID to `ALLOWED_USER_IDS` in `.env`

### Admin User Management

The bot includes admin commands to manage user access dynamically without editing the `.env` file:

**Setup:**
1. Set `ADMIN_USER_ID` in your `.env` file to your Telegram user ID
2. Ensure you're in the `ALLOWED_USER_IDS` list as well

**Admin Commands:**

**Adding a user:**
```
Admin: /add_user

Bot: 👤 Add New User
     Please enter the Telegram User ID you want to authorize.
     💡 Tip: Users can find their ID by sending any message to @userinfobot
     Enter the user ID (numbers only):

Admin: 987654321

Bot: ✅ User Added Successfully
     User ID 987654321 has been authorized.
     Total authorized users: 3
```

**Removing a user:**
```
Admin: /remove_user

Bot: 👤 Remove User
     Current authorized users:
     • 123456789
     • 555666777
     • 987654321
     Please enter the User ID you want to remove:

Admin: 555666777

Bot: ✅ User Removed Successfully
     User ID 555666777 has been removed from authorized users.
     Total authorized users: 2
```

**Listing users:**
```
Admin: /list_users

Bot: 👥 Authorized Users List
     Total: 2 user(s)
     
     1. 123456789
     2. 987654321
```

**Features:**
- Changes are written to the `.env` file immediately
- Bot updates its internal user list in real-time (no restart needed)
- Admin cannot remove themselves from the authorized list
- All admin actions are logged for security

**Security Notes:**
- Only the user with the `ADMIN_USER_ID` can execute admin commands
- Non-admin users attempting admin commands will receive an access denied message
- User additions/removals are logged with timestamps

## Advanced Configuration ⚙️

### Parallel Processing Limits

Edit `settings.py`:
```python
SEMAPHORE_LIMIT = 20  # Concurrent LLM requests
```

### Message Length

Telegram has a 4096 character limit. The bot automatically splits long messages:
```python
tg_notify_multiple(text, max_length=4000)
```

## Contributing 🤝

Feel free to:
- Report bugs
- Suggest features
- Submit pull requests
- Improve documentation

## Notes 📝

- Papers are stored in `papers.json` to avoid reprocessing
- The bot can handle multiple users simultaneously
- Each user's session is tracked independently
- Processing time depends on the number of papers and LLM speed

## Future Enhancements 🔮

- Natural language date input ("last week", "yesterday")
- Custom arXiv categories filtering
- Export to PDF/Markdown
- Scheduled automatic searches
- Knowledge graph generation

---

Built with ❤️ for researchers who want to stay current with arXiv

