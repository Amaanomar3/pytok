#!/bin/bash

# Script to manually run the TikTok scraper instead of waiting for the cron job

echo "Starting manual run of TikTok scraper..."

# Run the script in the Docker container with virtual display
docker exec -i tiktok-scraper bash -c "
# Set up virtual display
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 -ac > /dev/null 2>&1 &
sleep 2

# Run the scraper
cd /app && python /app/pythonScraper.py --headless true
"

echo "Manual run completed. Check logs at ./logs/scraper.log" 