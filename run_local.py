#!/usr/bin/env python3
"""
Local development runner for the TikTok Scraper service.
This sets up proper async event loop policies and runs the Quart app.
"""

import os
import platform
import asyncio
from pythonScraper import app

# Set the proper event loop policy based on platform
if platform.system() == 'Windows':
    # Windows requires a specific event loop policy
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    # Run with the Quart development server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    ) 