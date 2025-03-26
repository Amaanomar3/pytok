import logging
import os
import re
import time
import uuid  # Add uuid for instance IDs
from typing import Optional, Dict, Any

from browserforge.injectors.playwright import AsyncNewContext
from browserforge.headers import Browser as ForgeBrowser
from playwright.async_api import async_playwright
from undetected_playwright import Malenia

from .api.sound import Sound
from .api.user import User
from .api.search import Search
from .api.hashtag import Hashtag
from .api.video import Video
from .api.trending import Trending

from .exceptions import *
from .utils import LOGGER_NAME
from .captcha_solver import CaptchaSolver
from dataclasses import dataclass

os.environ["no_proxy"] = "127.0.0.1,localhost"

BASE_URL = "https://m.tiktok.com/"
DESKTOP_BASE_URL = "https://www.tiktok.com/"


class PyTok:
    _is_context_manager = False
    logger = logging.getLogger(LOGGER_NAME)
    
    # We'll use factory methods instead of class variables

    def __init__(
            self,
            logging_level: int = logging.WARNING,
            request_delay: Optional[int] = 0,
            headless: Optional[bool] = False,
            browser: Optional[str] = "chromium",
            manual_captcha_solves: Optional[bool] = False,
            log_captcha_solves: Optional[bool] = False,
            instance_id: Optional[str] = None,
    ):
        """The PyTok class. Used to interact with TikTok.

        ##### Parameters
        * logging_level: The logging level you want the program to run at, optional
            These are the standard python logging module's levels.

        * request_delay: The amount of time in seconds to wait before making a request, optional
            This is used to throttle your own requests as you may end up making too
            many requests to TikTok for your IP.

        * instance_id: Optional unique identifier for this instance
            If not provided, a random UUID will be generated.

        * **kwargs
            Parameters that are passed on to basically every module and methods
            that interact with this main class. These may or may not be documented
            in other places.
        """

        self._headless = headless
        self._request_delay = request_delay
        self._browser_type = browser  # Renamed to avoid conflict with instance
        self._manual_captcha_solves = manual_captcha_solves
        self._log_captcha_solves = log_captcha_solves
        
        # Assign a unique ID to this instance
        self.instance_id = instance_id or str(uuid.uuid4())
        
        # Stats tracking
        self.created_at = time.time()
        self.request_count = 0
        self.successful_requests = 0
        self.failed_requests = 0

        self.logger.setLevel(logging_level)
        self.logger = logging.getLogger(f"{LOGGER_NAME}_{self.instance_id}")
        self.logger.setLevel(logging_level)

        # Create a local instance attribute to store API parent references
        self._api_classes = {}
        
        self.request_cache = {}
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
    
    # Factory methods for API classes that set this instance as parent
    def user(self, **kwargs) -> User:
        """Create a User instance with this PyTok instance as parent"""
        try:
            user_instance = User(**kwargs)
            # Explicitly set parent as instance attribute
            user_instance.parent = self
            return user_instance
        except Exception as e:
            self.logger.error(f"Error creating User instance: {str(e)}")
            # Create minimal user instance
            user_instance = User(username=kwargs.get('username'), user_id=kwargs.get('user_id'), sec_uid=kwargs.get('sec_uid'))
            user_instance.parent = self
            return user_instance
    
    def search(self, **kwargs) -> Search:
        """Create a Search instance with this PyTok instance as parent"""
        try:
            search_term = kwargs.get('search_term', '')
            search_instance = Search(search_term=search_term, parent=self)
            # Explicitly set parent as instance attribute
            search_instance.parent = self
            return search_instance
        except Exception as e:
            self.logger.error(f"Error creating Search instance: {str(e)}")
            # Create minimal search instance
            search_term = kwargs.get('search_term', '')
            search_instance = Search(search_term=search_term, parent=self)
            search_instance.parent = self
            return search_instance
    
    def sound(self, **kwargs) -> Sound:
        """Create a Sound instance with this PyTok instance as parent"""
        try:
            sound_instance = Sound(**kwargs, parent=self)
            # Explicitly set parent as instance attribute
            sound_instance.parent = self
            return sound_instance
        except Exception as e:
            self.logger.error(f"Error creating Sound instance: {str(e)}")
            # Create minimal sound instance
            sound_instance = Sound(id=kwargs.get('id'), parent=self)
            sound_instance.parent = self
            return sound_instance
    
    def hashtag(self, **kwargs) -> Hashtag:
        """Create a Hashtag instance with this PyTok instance as parent"""
        try:
            hashtag_instance = Hashtag(**kwargs, parent=self)
            # Explicitly set parent as instance attribute
            hashtag_instance.parent = self
            return hashtag_instance
        except Exception as e:
            self.logger.error(f"Error creating Hashtag instance: {str(e)}")
            # Create minimal hashtag instance
            hashtag_instance = Hashtag(name=kwargs.get('name'), id=kwargs.get('id'), parent=self)
            hashtag_instance.parent = self
            return hashtag_instance
    
    def video(self, **kwargs) -> Video:
        """Create a Video instance with this PyTok instance as parent"""
        try:
            video_instance = Video(**kwargs)
            # Explicitly set parent as instance attribute
            video_instance.parent = self
            return video_instance
        except Exception as e:
            self.logger.error(f"Error creating Video instance: {str(e)}")
            # Create minimal video instance with just ID
            video_instance = Video(id=kwargs.get('id'))
            video_instance.parent = self
            return video_instance
    
    def trending(self, **kwargs) -> Trending:
        """Create a Trending instance with this PyTok instance as parent"""
        try:
            trending_instance = Trending(parent=self)
            # Explicitly set parent as instance attribute
            trending_instance.parent = self
            return trending_instance
        except Exception as e:
            self.logger.error(f"Error creating Trending instance: {str(e)}")
            # Create minimal trending instance
            trending_instance = Trending(parent=self)
            trending_instance.parent = self
            return trending_instance

    async def __aenter__(self):
        self.logger.info(f"Initializing PyTok instance {self.instance_id}")
        self._playwright = await async_playwright().start()
        fingerprint_options = {}
        if self._browser_type == "firefox":
            self._browser = await self._playwright.firefox.launch(headless=self._headless)
            fingerprint_options['browser'] = [ForgeBrowser("firefox")]
        elif self._browser_type == "chromium":
            self._browser = await self._playwright.chromium.launch(headless=self._headless)
            fingerprint_options['browser'] = 'chrome'
        else:
            raise Exception("Browser not supported")
        self._context = await AsyncNewContext(self._browser, fingerprint_options=fingerprint_options)
        device_config = self._playwright.devices['Desktop Chrome']
        self._context = await self._browser.new_context(**device_config)
        await Malenia.apply_stealth(self._context)
        self._page = await self._context.new_page()

        # move mouse to 0, 0 to have known mouse start position
        await self._page.mouse.move(0, 0)

        self._requests = []
        self._responses = []

        self._page.on("request", lambda request: self._requests.append(request))

        async def save_responses_and_body(response):
            self._responses.append(response)
            try:
                response._body = await response.body()
            except Exception:
                pass

        self._page.on("response", save_responses_and_body)

        self._user_agent = await self._page.evaluate("() => navigator.userAgent")
        self._is_context_manager = True
        self.logger.info(f"PyTok instance {self.instance_id} initialized successfully")
        return self

    async def request_delay(self):
        if self._request_delay is not None:
            await self._page.wait_for_timeout(self._request_delay * 1000)

    def __del__(self):
        """A basic cleanup method, called automatically from the code"""
        if not self._is_context_manager:
            self.logger.debug(
                f"PyTok instance {self.instance_id} was shutdown improperly. Ensure the instance is terminated with .shutdown()"
            )
            self.shutdown()
        return

    #
    # PRIVATE METHODS
    #

    def r1(self, pattern, text):
        m = re.search(pattern, text)
        if m:
            return m.group(1)

    async def shutdown(self) -> None:
        self.logger.info(f"Shutting down PyTok instance {self.instance_id}")
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            self.logger.error(f"Error during shutdown of instance {self.instance_id}: {str(e)}")
        finally:
            if self._headless:
                display = getattr(self, "_display", None)
                if display:
                    display.stop()
            self.logger.info(f"PyTok instance {self.instance_id} shutdown complete")

    async def __aexit__(self, type, value, traceback):
        await self.shutdown()

    async def get_ms_tokens(self):
        all_cookies = await self._context.cookies()
        cookie_name = 'msToken'
        cookies = []
        for cookie in all_cookies:
            if cookie["name"] == cookie_name and cookie['secure']:
                cookies.append(cookie['value'])
        if len(cookies) == 0:
            raise Exception(f"Could not find {cookie_name} cookie")
        return cookies
