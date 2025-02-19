import discord
from discord.ext import tasks
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import os
from dotenv import load_dotenv
import asyncio  # Add asyncio import
from datetime import datetime, timedelta
import yaml
import logging
import time
from selenium.common.exceptions import WebDriverException
import functools
from selenium.common.exceptions import WebDriverException, TimeoutException, StaleElementReferenceException
import backoff  # Add to requirements.txt

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('arcs_bot')

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
NOTIFICATION_TARGETS = [int(id.strip()) for id in os.getenv('NOTIFICATION_TARGETS', '').split(',')]
TARGET_URL = os.getenv('TARGET_URL')
ARCS_PAGE_LOAD_WAIT = int(os.getenv('ARCS_PAGE_LOAD_WAIT', 40))  # Convert to integer
SELENIUM_URL = os.getenv('SELENIUM_URL', 'http://localhost:4444/wd/hub')

# Load player configurations
with open('players.yml', 'r') as file:
    config = yaml.safe_load(file)
    PLAYERS = config['players']

def retry_selenium_operation(max_tries=3, delay=5):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            for attempt in range(max_tries):
                try:
                    return await func(self, *args, **kwargs)
                except (WebDriverException, TimeoutException) as e:
                    logger.warning(f"Selenium operation failed (attempt {attempt + 1}/{max_tries}): {str(e)}")
                    if attempt == max_tries - 1:
                        logger.error("Max retries reached, reconnecting driver")
                        await self.reconnect_driver()
                        raise
                    await asyncio.sleep(delay)
            return None
        return wrapper
    return decorator

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
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to connect to Selenium (attempt {attempt + 1}/{max_retries})")
                self.driver = webdriver.Remote(
                    command_executor=SELENIUM_URL,
                    options=chrome_options
                )
                logger.info(f"Successfully connected to Selenium at {SELENIUM_URL}")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Failed to connect to Selenium: {str(e)}")
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to Selenium after all retries")
                    raise

    def get_player_mention(self, color):
        """Get discord mention string for a player color"""
        if color in PLAYERS:
            return f"<@{PLAYERS[color]}>"
        return f"@{color}"

    async def setup_hook(self):
        try:
            # Initial page load during setup
            self.driver.get(TARGET_URL)
            await asyncio.sleep(ARCS_PAGE_LOAD_WAIT)  # Use the integer value
            self.page_loaded = True
            logger.info("Initial page load complete")
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

    async def reconnect_driver(self):
        """Reconnect the Selenium driver"""
        logger.info("Reconnecting Selenium driver...")
        try:
            if hasattr(self, 'driver'):
                try:
                    self.driver.quit()
                except:
                    pass
            self.setup_driver()
            self.page_loaded = False
            logger.info("Driver reconnected successfully")
        except Exception as e:
            logger.error(f"Failed to reconnect driver: {str(e)}")
            raise

    @retry_selenium_operation()
    async def get_current_turn(self):
        """Get the current turn information with retries"""
        if not self.page_loaded:
            self.driver.get(TARGET_URL)
            await asyncio.sleep(ARCS_PAGE_LOAD_WAIT)
            self.page_loaded = True
        else:
            self.driver.refresh()
            await asyncio.sleep(5)

        body_element = WebDriverWait(self.driver, ARCS_PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return body_element.text

    @tasks.loop(minutes=int(os.getenv('ARCS_CHECK_INTERVAL', 15)))
    async def check_turn(self):
        try:
            body_text = await self.get_current_turn()
            
            # Look for the complete "Waiting for [Color]" text in the body
            wait_text = None
            for line in body_text.split('\n'):
                if line.strip().startswith('Waiting for'):
                    wait_text = line.strip()
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
                            logger.info(f"Still {color}'s turn. Next reminder in {hours_until:.1f}h")
            else:
                logger.info("No turn information found")
            
        except Exception as e:
            logger.error(f"Error in check_turn: {str(e)}", exc_info=True)
            self.page_loaded = False
            await asyncio.sleep(30)  # Wait before retrying

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
        self.check_turn.start()  # Start the check_turn task here

client = TurnNotifierBot()
client.run(DISCORD_TOKEN)
