# Arcs Turn Notifier Bot

A Discord bot that monitors an Arcs game and notifies players when it's their turn.

## Features

- Monitors Arcs game URL for turn changes
- Notifies players in Discord when it's their turn
- Sends reminders after 24 hours of inactivity
- Supports multiple notification channels/threads
- Docker support for easy deployment

## Prerequisites

- Python 3.11+
- Chrome/Chromium browser
- Discord Bot Token
- Discord Server with channels/threads for notifications

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd arcs
   ```

2. **Create and configure .env file:**
   ```properties
   # Discord Bot Token from Discord Developer Portal
   DISCORD_TOKEN=your_bot_token_here
   
   # Comma-separated channel/thread IDs for notifications
   NOTIFICATION_TARGETS=channel_id_1,channel_id_2
   
   # URL of your Arcs game
   TARGET_URL=https://hrf.im/play/arcs/your-game-id
   ```

3. **Create players.yml:**
   Example in Configuration Details section.

4. **Setup using Docker (recommended):**
   ```bash
   docker-compose up -d
   ```

   Or manually:
   ```bash
   pip install -r requirements.txt
   python bot.py
   ```

   Pre built images available at
   https://hub.docker.com/r/naterd/arcs-turn-notifier/tags


## Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a New Application
3. Go to "Bot" section and create a bot
4. Enable these Privileged Intents:
   - Message Content Intent
   - Server Members Intent
5. Copy the bot token for .env file
6. Generate invite link with these permissions:
   - Send Messages
   - View Channels
7. Invite bot to your server

## Getting Discord IDs

To get User/Channel IDs:
1. Enable Developer Mode in Discord (Settings -> App Settings -> Advanced)
2. Right-click user/channel -> Copy ID

## Configuration Details

### players.yml
Maps game colors to Discord user IDs:
```yaml
players:
  Red: "151213534566664363436"    # Example user ID
  White: "14353452252225252522"
  Yellow: "1263463666363232262"
```

### Environment Variables
- `DISCORD_TOKEN`: Your bot's token
- `NOTIFICATION_TARGETS`: Channel/thread IDs for notifications
- `TARGET_URL`: URL of the Arcs game to monitor
- `ARCS_CHECK_INTERVAL`: How often in minutes you want it to check for whose turn it is, defaults to 15 minutes
- `ARCS_PAGE_LOAD_WAIT`: Sometimes it can be slow loading the game page based on load of the server, defaults to 40 seconds, increase if you have problems detecting turns because it requires the page to be fully loaded
- `LOG_LEVEL`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL), defaults to INFO
- `SELENIUM_URL`: URL of the Selenium instance, defaults to http://localhost:4444/wd/hub

## Selenium Configuration

The bot uses Selenium with Chrome in headless mode. The docker-compose setup includes:
- Standalone Chrome container with health checks
- 2GB shared memory size for stability
- Configurable session management
- Automatic retry mechanism for connection issues

## Contributing

Feel free to open issues or submit pull requests!

## License

MIT License
