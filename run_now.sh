#!/bin/bash

# Script to manually run the TikTok scraper instead of waiting for the cron job

echo "Starting manual run of TikTok scraper..."
docker exec tiktok-scraper python /app/pythonScraper.py
echo "Manual run completed. Check logs at ./logs/scraper.log" 