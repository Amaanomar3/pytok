# Running TikTok Scraper Locally

This guide provides instructions for setting up and running the TikTok Scraper service on your local machine for development.

## Prerequisites

- Python 3.7 or higher
- pip (Python package manager)
- Git (optional, for cloning the repository)

## Step 1: Set Up the Environment

First, create and activate a virtual environment:

### On Windows:

```powershell
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
.\venv\Scripts\Activate.ps1
# or
.\venv\Scripts\activate.bat  # For cmd.exe
```

### On macOS/Linux:

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

## Step 2: Install Dependencies

Install the required packages:

```bash
pip install -r requirements.txt
```

## Step 3: Install Playwright Dependencies

Install the required browser binaries for Playwright:

```bash
playwright install
playwright install-deps
```

## Step 4: Run the Application

You can run the application using the provided runner script:

```bash
python run_local.py
```

This will start the development server at `http://localhost:5000`.

### Alternative Method

Alternatively, you can run the application using Hypercorn directly:

```bash
# For development
hypercorn pythonScraper:app --reload --bind 0.0.0.0:5000

# For testing production setup
hypercorn asgi:app --bind 0.0.0.0:5000
```

## Step 5: Test the API

Once the server is running, you can test the API using your browser or tools like curl:

```bash
curl "http://localhost:5000/tiktok/user/videos?username=example_username"
```

Or simply open the following URL in your browser:

```
http://localhost:5000/tiktok/user/videos?username=example_username
```

## Troubleshooting

### Common Issues

1. **Event loop policy errors on Windows**:
   If you encounter errors related to the event loop on Windows, make sure you're using the provided `run_local.py` script which sets the appropriate event loop policy.

2. **Browser initialization failures**:
   Make sure Playwright dependencies are installed correctly:
   ```bash
   playwright install
   playwright install-deps
   ```

3. **Port already in use**:
   If port 5000 is already in use, modify the port number in `run_local.py` or use the Hypercorn command with a different port.

4. **TikTok blocking requests**:
   TikTok may temporarily block requests if you make too many in a short period. If this happens, try using a different username or wait a while before trying again.

### Debugging

To enable more detailed logging, you can modify the logging level in `pythonScraper.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

## Using with Frontend Applications

For frontend development, you might need to enable CORS. This can be done by adding the following to your `pythonScraper.py`:

```python
from quart_cors import cors

app = Quart(__name__)
app = cors(app, allow_origin="*")
```

Remember to install the CORS extension:

```bash
pip install quart-cors
``` 