#!/usr/bin/env python3
"""
ASGI entry point for the TikTok Scraper service.
Used for production deployment with Hypercorn.
"""

from pythonScraper import app

# This file is used by Hypercorn to load the application
# Command example: hypercorn asgi:app 