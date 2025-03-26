FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies for browsers and cron
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    procps \
    libglib2.0-0 \
    libnss3 \
    libxcb1 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN python -m playwright install chromium --with-deps

# Copy project files
COPY pythonScraper.py .
COPY .env .

# Create log directory
RUN mkdir -p /app/logs

# Create crontab file to run daily at midnight (UTC)
RUN echo "0 0 * * * cd /app && python /app/pythonScraper.py --headless true >> /app/logs/scraper.log 2>&1" > /etc/cron.d/tiktok-scraper
RUN chmod 0644 /etc/cron.d/tiktok-scraper
RUN crontab /etc/cron.d/tiktok-scraper

# Create entrypoint script
RUN echo '#!/bin/bash\nservice cron start\ntail -f /app/logs/scraper.log' > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Command to run
CMD ["/app/entrypoint.sh"] 