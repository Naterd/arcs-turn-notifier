import discord
from discord.ext import tasks
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import os
from dotenv import load_dotenv
import asyncio  # Add asyncio import
from datetime import datetime, timedelta
import yaml
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('arcs_bot')

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
NOTIFICATION_TARGETS = [int(id.strip()) for id in os.getenv('NOTIFICATION_TARGETS', '').split(',')]
TARGET_URL = os.getenv('TARGET_URL')

# Load player configurations
with open('players.yml', 'r') as file:
    config = yaml.safe_load(file)
PLAYERS = config['players']

class TurnNotifierBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Add members intent
        intents.messages = True  # Add messages intent
        super().__init__(intents=intents)
        self.last_turn = None
        self.last_color = None  # Add tracking for last color
        self.last_color_change_time = None
        self.last_notification_time = None
        self.setup_driver()
        self.page_loaded = False
    
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")  # Set window size
        self.driver = webdriver.Chrome(options=chrome_options)

    def get_player_mention(self, color):
        """Get discord mention string for a player color"""
        if color in PLAYERS:
            return f"<@{PLAYERS[color]}>"
        return f"@{color}"

    async def setup_hook(self):
        try:
            # Initial page load during setup
            self.driver.get(TARGET_URL)
            await asyncio.sleep(40)  # Wait for initial load
            self.page_loaded = True
            logger.info("Initial page load complete")
            self.check_turn.start()
        except Exception as e:
            logger.error(f"Error during initial page load: {str(e)}")
            self.page_loaded = False

    async def send_to_targets(self, message):
        """Send message to all configured channels and threads"""
        logger.debug(f"Attempting to send message: {message}")
        for target_id in NOTIFICATION_TARGETS:
            try:
                # Try to get as channel first
                target = self.get_channel(target_id)
                
                if not target:
                    # If not a channel, try to get as thread
                    for guild in self.guilds:
                        for channel in guild.channels:
                            if hasattr(channel, 'threads'):
                                thread = discord.utils.get(channel.threads, id=target_id)
                                if thread:
                                    target = thread
                                    break
                
                if target:
                    await target.send(message)
                    logger.info(f"Message sent to {target.name} ({target_id})")
                else:
                    logger.warning(f"Could not find channel/thread {target_id}")
            
            except discord.Forbidden:
                logger.error(f"No permission to send to {target_id}")
            except Exception as e:
                logger.error(f"Error sending to {target_id}: {str(e)}")

    @tasks.loop(minutes=1)
    async def check_turn(self):
        try:
            if not self.page_loaded:
                logger.info("Performing full page load...")
                self.driver.get(TARGET_URL)
                await asyncio.sleep(os.environ.get('ARCS_PAGE_LOAD_WAIT', 40))  # Wait for page to load
                self.page_loaded = True
            else:
                logger.debug("Refreshing page...")
                self.driver.refresh()
                await asyncio.sleep(5)
            
            # Get the full text content first
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            logger.debug(f"Page content preview: {body_text[:200]}")
            
            # Look for the complete "Waiting for [Color]" text in the body
            wait_text = None
            for line in body_text.split('\n'):
                line = line.strip()
                if line.startswith('Waiting for'):
                    wait_text = line
                    logger.debug(f"Found turn status: {wait_text}")
                    break
            
            if wait_text and len(wait_text.split()) >= 3:  # Ensure we have "Waiting for [Color]"
                color = wait_text.split('Waiting for ', 1)[1].strip()
                current_time = datetime.now()
                
                if color:
                    player_handle = self.get_player_mention(color)
                    if color != self.last_color:  # Only notify if color changed
                        status_message = f"Waiting for {player_handle} to take their turn"
                        logger.info(f"Turn changed: {self.last_color} -> {color}")
                        self.last_color = color  # Update last color
                        self.last_color_change_time = current_time
                        self.last_notification_time = current_time
                        await self.send_to_targets(status_message)
                    else:
                        # Same color - check if 24 hours have passed since last notification
                        if (self.last_notification_time and 
                            current_time - self.last_notification_time >= timedelta(hours=24)):
                            hours_waiting = (current_time - self.last_color_change_time).total_seconds() / 3600
                            logger.info(f"Sending 24h reminder for {color} ({int(hours_waiting)}h)")
                            reminder_message = f"Still waiting for {player_handle} its been 24 hours"
                            self.last_notification_time = current_time
                            await self.send_to_targets(reminder_message)
                        else:
                            hours_until = 24 - ((current_time - self.last_notification_time).total_seconds() / 3600)
                            logger.debug(f"Still {color}'s turn. Next reminder in {hours_until:.1f}h")
            else:
                logger.debug("No turn information found")
            
        except Exception as e:
            logger.error(f"Error checking turn: {e}", exc_info=True)
            self.page_loaded = False

    async def close(self):
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
            except:
                pass
        await super().close()
    
    def __del__(self):
        try:
            if hasattr(self, 'driver'):
                self.driver.quit()
        except:
            pass

    @check_turn.before_loop
    async def before_check_turn(self):
        await self.wait_until_ready()

    async def on_ready(self):
        logger.info(f"Bot {self.user} has connected to Discord")

client = TurnNotifierBot()
client.run(DISCORD_TOKEN)
