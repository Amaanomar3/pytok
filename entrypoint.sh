#!/bin/bash
  # Create log directory and file if they don't exist
  mkdir -p /app/logs
  touch /app/logs/scraper.log
  chmod 666 /app/logs/scraper.log

  # Start cron service
  service cron start
  echo "$(date): Container started, cron service running" >> /app/logs/scraper.log

  # Keep container running and follow the log
  tail -f /app/logs/scraper.log
