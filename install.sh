#!/bin/bash

# Installation script for TikTok scraper on Linux VPS

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed successfully."
    echo "Please log out and log back in for Docker permissions to take effect."
    echo "Then run this script again."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose is not installed. Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "Docker Compose installed successfully."
fi

# Create .env file from example if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit the .env file with your MongoDB credentials and settings:"
    echo "nano .env"
fi

# Create logs directory
mkdir -p logs
chmod 777 logs

# Make scripts executable
chmod +x run_now.sh

# Build and start the container
echo "Building and starting the TikTok scraper container..."
docker-compose up -d --build

echo ""
echo "TikTok scraper has been deployed!"
echo "The scraper will run daily at midnight UTC."
echo ""
echo "You can run the scraper manually with:"
echo "./run_now.sh"
echo ""
echo "To view logs:"
echo "cat logs/scraper.log"
echo ""
echo "To stop the service:"
echo "docker-compose down" 