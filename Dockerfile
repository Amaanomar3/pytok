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
    xvfb \
    xauth \
    python3-tk \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pyvirtualdisplay

# Install Playwright browsers
RUN python -m playwright install chromium --with-deps

# Copy project files
COPY pythonScraper.py .
COPY pytok/ /app/pytok/
COPY .env .

# Create log directory
RUN mkdir -p /app/logs

# Create crontab file to run daily at midnight (UTC)
RUN echo "0 0 * * * export DISPLAY=:99 && cd /app && Xvfb :99 -screen 0 1920x1080x24 -ac > /dev/null 2>&1 & sleep 2 && python /app/pythonScraper.py --headless true >> /app/logs/scraper.log 2>&1" > /etc/cron.d/tiktok-scraper
RUN chmod 0644 /etc/cron.d/tiktok-scraper
RUN crontab /etc/cron.d/tiktok-scraper

# Create entrypoint script with virtual display
RUN echo '#!/bin/bash\n\
# Start virtual display\n\
export DISPLAY=:99\n\
Xvfb :99 -screen 0 1920x1080x24 -ac > /dev/null 2>&1 &\n\
sleep 2\n\
\n\
# Create log file if it doesn't exist\n\
mkdir -p /app/logs\n\
touch /app/logs/scraper.log\n\
chmod 666 /app/logs/scraper.log\n\
\n\
# Start cron service\n\
service cron start\n\
echo "$(date): Container started, cron service running" >> /app/logs/scraper.log\n\
\n\
# Keep container running and follow the log\n\
tail -f /app/logs/scraper.log' > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Command to run
CMD ["/app/entrypoint.sh"] 
