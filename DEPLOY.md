# Deploying TikTok Scraper Flask Service

This guide provides step-by-step instructions for deploying the TikTok Scraper service on a Debian 11 VPS using Nginx as a reverse proxy.

## Prerequisites

- A Debian 11 VPS with root or sudo access
- A domain name (optional, but recommended)
- Basic knowledge of Linux command line

## 1. Install Required Packages

Update your system and install necessary packages:

```bash
# Update package lists
sudo apt update

# Install Python, pip, and virtualenv
sudo apt install -y python3 python3-pip python3-venv

# Install Nginx and supervisor
sudo apt install -y nginx supervisor
```

## 2. Set Up Your Application

```bash
# Create a directory for your application
sudo mkdir -p /var/www/tiktok-scraper

# Copy your application files to the server
# Option 1: Using SCP
scp -r /path/to/your/local/app/* user@your_server_ip:/var/www/tiktok-scraper/

# Option 2: Using Git
cd /var/www
sudo git clone https://your-repository-url.git tiktok-scraper

# Set proper permissions
sudo chown -R www-data:www-data /var/www/tiktok-scraper
```

## 3. Create a Python Virtual Environment

```bash
# Navigate to your application directory
cd /var/www/tiktok-scraper

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Install hypercorn (ASGI server for Quart)
pip install hypercorn

# Install playwright dependencies
playwright install-deps
playwright install
```

## 4. Create a ASGI Entry Point

Create a file named `asgi.py` in your application directory:

```python
from pythonScraper import app

if __name__ == "__main__":
    app.run()
```

## 5. Configure Supervisor

Supervisor ensures your application stays running even after server restarts.

```bash
# Create log directory
sudo mkdir -p /var/log/tiktok-scraper
sudo chown -R www-data:www-data /var/log/tiktok-scraper

# Create supervisor configuration
sudo nano /etc/supervisor/conf.d/tiktok-scraper.conf
```

Add the following content to the configuration file:

```
[program:tiktok-scraper]
directory=/var/www/tiktok-scraper
command=/var/www/tiktok-scraper/venv/bin/hypercorn --workers 4 --bind unix:/var/www/tiktok-scraper/tiktok-scraper.sock asgi:app
autostart=true
autorestart=true
stderr_logfile=/var/log/tiktok-scraper/error.log
stdout_logfile=/var/log/tiktok-scraper/access.log
user=www-data
group=www-data
environment=PATH="/var/www/tiktok-scraper/venv/bin"
stopasgroup=true
killasgroup=true
```

## 6. Configure Nginx

Create a new site configuration:

```bash
sudo nano /etc/nginx/sites-available/tiktok-scraper
```

Add the following configuration:

```
server {
    listen 80;
    server_name your_domain_or_ip;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/tiktok-scraper/tiktok-scraper.sock;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        
        # WebSocket support (needed for Quart)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/tiktok-scraper /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # Optional: remove default site

# Test the Nginx configuration
sudo nginx -t
```

## 7. Start Services

```bash
# Reload supervisor to pick up the new configuration
sudo supervisorctl reread
sudo supervisorctl update

# Restart Nginx
sudo systemctl restart nginx
```

## 8. Set Up Firewall (Optional but Recommended)

```bash
sudo apt install -y ufw
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 9. Configure SSL with Let's Encrypt (Optional but Recommended)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain and install certificate
sudo certbot --nginx -d your_domain
```

## 10. Test Your Deployment

Visit your domain or IP address in a browser and try accessing your API endpoint:

```
http://your_domain_or_ip/tiktok/user/videos?username=example_username
```

## Troubleshooting

If you encounter issues, check the following logs:

```bash
# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Application logs
sudo tail -f /var/log/tiktok-scraper/error.log
sudo tail -f /var/log/tiktok-scraper/access.log

# Supervisor logs
sudo tail -f /var/log/supervisor/supervisord.log
```

### Common Issues and Solutions

1. **Browser automation issues**: Make sure Playwright dependencies are installed correctly:
   ```bash
   cd /var/www/tiktok-scraper
   source venv/bin/activate
   playwright install-deps
   ```

2. **Permission issues**: Ensure proper permissions for your application directory:
   ```bash
   sudo chown -R www-data:www-data /var/www/tiktok-scraper
   sudo chmod -R 755 /var/www/tiktok-scraper
   ```

3. **Socket connection issues**: Check if the socket file exists and has correct permissions:
   ```bash
   ls -la /var/www/tiktok-scraper/tiktok-scraper.sock
   sudo chown www-data:www-data /var/www/tiktok-scraper/tiktok-scraper.sock
   ```

4. **Headless browser issues**: For running headless browser on servers without display:
   ```bash
   sudo apt install -y xvfb
   ```
   
   Then modify your supervisor configuration to use Xvfb:
   ```
   environment=PATH="/var/www/tiktok-scraper/venv/bin",DISPLAY=":99"
   ```

## Updating the Application

To update your application:

```bash
# Navigate to your application directory
cd /var/www/tiktok-scraper

# Pull latest changes (if using Git)
sudo git pull

# Activate the virtual environment
source venv/bin/activate

# Install any new requirements
pip install -r requirements.txt

# Restart the application
sudo supervisorctl restart tiktok-scraper

# Check status
sudo supervisorctl status tiktok-scraper
```

## Performance Considerations

- For high traffic, consider increasing the number of Hypercorn workers
- Monitor memory usage as headless browsers can be resource-intensive
- Consider implementing caching for frequently requested data
- For very high loads, consider scaling horizontally with multiple servers

## Browser Pool Configuration

The TikTok scraper now implements a browser pool to reuse browser instances across requests. This significantly improves performance by:

1. Reducing the overhead of starting and closing browsers for each request
2. Maintaining a fixed number of browser instances to control memory usage
3. Implementing automatic cleanup of idle browsers

You can configure the browser pool by modifying these parameters in `pythonScraper.py`:

```python
browser_pool = BrowserPool(
    max_browsers=3,  # Maximum number of browsers to keep in the pool
    browser_ttl=300  # Time in seconds before an unused browser is closed (5 minutes)
)
```

For production environments, you may want to adjust these settings based on:

- Your server's available memory (each browser instance requires ~100-200MB)
- The number of concurrent requests your service typically handles
- The desired balance between performance and resource usage

### Monitoring Browser Pool Usage

The application now includes improved logging to monitor browser pool activity. To check these logs:

```bash
sudo tail -f /var/log/tiktok-scraper/access.log
```

Look for log entries showing:
- "Creating new browser" - A new browser instance is being created
- "Browser successfully created" - A browser was initialized successfully
- "Reusing existing browser" - A browser from the pool is being reused
- "Browser returned to pool" - A browser was returned to the pool after use
- "Waiting for browser to become available" - Request is waiting for a browser
- "Browser closed (pool full)" - A browser was closed because the pool is at maximum capacity
- "Closed expired browser" - A browser was closed because it exceeded its TTL

### Concurrent Request Handling

The application has been updated from Flask to Quart, which is an asynchronous framework that allows true concurrent processing of requests. This means:

1. Multiple requests can be processed simultaneously using the same worker
2. The application can efficiently handle waiting for browsers to become available
3. Long-running TikTok scraping operations won't block other requests

This change significantly improves the application's ability to handle multiple simultaneous requests without deadlocking or timeouts.

### Memory Usage Considerations

If you encounter memory issues:

1. Decrease `max_browsers` to limit the number of concurrent browser instances
2. Decrease `browser_ttl` to close idle browsers sooner
3. Consider adding a memory monitoring solution that can restart the service if memory usage gets too high

For proper cleanup when the application restarts or shuts down:

```
[program:tiktok-scraper]
// ... existing config ...
stopasgroup=true
killasgroup=true
``` 