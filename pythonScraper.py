import asyncio
import uuid
import logging
import sys
import time
from pytok.tiktok import PyTok
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
import argparse
from typing import List, Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tiktok_scraper.log")
    ]
)
logger = logging.getLogger(__name__)

# MongoDB Configuration - Use the existing database settings
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.environ.get("DB_NAME", "tiktok_data")
POSTS_COLLECTION = os.environ.get("POSTS_COLLECTION", "posts")
CREATOR_COLLECTION = os.environ.get("CREATOR_COLLECTION", "Creator")

# Initialize MongoDB connection
mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]
posts_collection = db[POSTS_COLLECTION]
creator_collection = db[CREATOR_COLLECTION]

# Scraper Configuration
NUM_BROWSERS = int(os.environ.get("NUM_BROWSERS", "2"))
MAX_ACCOUNTS_PER_BROWSER = int(os.environ.get("MAX_ACCOUNTS_PER_BROWSER", "20"))
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

# Global state for browser management
browsers = [None] * NUM_BROWSERS
is_processing = [False] * NUM_BROWSERS
browser_locks = [asyncio.Lock() for _ in range(NUM_BROWSERS)]
browser_uuids = [str(uuid.uuid4()) for _ in range(NUM_BROWSERS)]
browser_accounts_processed = [0] * NUM_BROWSERS

async def get_browser(browser_id):
    """Initialize or rotate a browser"""
    global browsers, browser_accounts_processed
    try:
        # Check if browser needs rotation
        if browsers[browser_id] is not None and browser_accounts_processed[browser_id] >= MAX_ACCOUNTS_PER_BROWSER:
            logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) has processed {browser_accounts_processed[browser_id]} accounts, rotating...")
            try:
                await browsers[browser_id].__aexit__(None, None, None)
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) was closed for rotation")
            except Exception as close_err:
                logger.error(f"Error closing browser {browser_id} during rotation: {str(close_err)}")
            finally:
                browsers[browser_id] = None
                browser_uuids[browser_id] = str(uuid.uuid4())
                browser_accounts_processed[browser_id] = 0
                
        if browsers[browser_id] is None:
            browser_uuid = browser_uuids[browser_id]
            logger.info(f"Creating new browser instance for browser_id {browser_id}, UUID: {browser_uuid}")
            browser = PyTok(
                headless=HEADLESS,
                browser="chromium",
                logging_level=logging.INFO,
                request_delay=1,
                manual_captcha_solves=False,
                instance_id=browser_uuid
            )
            # Add stats to the PyTok instance
            browser.created_at = time.time()
            browser.request_count = 0
            browser.successful_requests = 0
            browser.failed_requests = 0
            
            await browser.__aenter__()
            logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) successfully initialized")
            browsers[browser_id] = browser
        return browsers[browser_id]
    except Exception as e:
        logger.error(f"Failed to initialize browser {browser_id}: {str(e)}")
        is_processing[browser_id] = False
        browsers[browser_id] = None
        raise

async def check_browser_health(browser_id):
    """Periodically check if browser is responsive and restart if needed"""
    while True:
        if browsers[browser_id] is not None and is_processing[browser_id]:
            try:
                await browsers[browser_id]._page.evaluate("1+1")
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) health check passed")
            except Exception as e:
                logger.error(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) health check failed: {str(e)}")
                is_processing[browser_id] = False
                try:
                    if browsers[browser_id]:
                        await browsers[browser_id].__aexit__(None, None, None)
                except Exception as close_error:
                    logger.error(f"Error closing unhealthy browser {browser_id}: {str(close_error)}")
                finally:
                    browsers[browser_id] = None
            
        await asyncio.sleep(60)  # Check every minute

async def process_account(browser_id, username, team_id):
    """Process a single TikTok account and store videos to MongoDB"""
    job_id = str(uuid.uuid4())[:8]
    browser_uuid = browser_uuids[browser_id]
    
    logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) processing {username} (team: {team_id})")
    
    try:
        browser = await get_browser(browser_id)
        browser.request_count += 1
        
        # Process the request
        user = browser.user(username=username)
        user_data = await user.info()

        videos = []
        count = 0
        max_videos = 10000
        videos_added = 0
        
        # Calculate today's date boundaries
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        start_of_day = datetime.strptime(today_str, "%Y-%m-%d")
        end_of_day = start_of_day + timedelta(days=1)
        
        logger.info(f"Processing {username} for team {team_id}, today: {today_str}")
        
        try:
            async for video in user.videos():
                try:
                    video_data = await video.info()
                    post_id = video_data.get("id", "")
                    
                    if not post_id:
                        logger.warning(f"Skipping video without ID for {username}")
                        continue
                    
                    # Add basic info to videos list (for logging)
                    video_summary = {
                        "id": post_id,
                        "createTime": video_data.get("createTime", 0),
                    }
                    
                    if video_summary in videos:
                        continue
                        
                    videos.append(video_summary)
                    count += 1
                    
                    # Following the logic from the old script:
                    # 1. Delete any posts from today with the same postId
                    result = posts_collection.delete_many({
                        "postId": post_id,
                        "teamId": team_id,
                        "createdAt": {"$gte": start_of_day, "$lt": end_of_day}
                    })
                    
                    if result.deleted_count > 0:
                        logger.info(f"Deleted {result.deleted_count} existing posts from today for postId {post_id}")
                    
                    # 2. Create and save the new post
                    current_time = datetime.utcnow()
                    post_document = {
                        "postId": post_id,
                        "viewCount": video_data.get("stats", {}).get("playCount", 0),
                        "teamId": team_id,
                        "accountName": username,
                        "uploadDate": video_data.get("createTime", int(time.time())),
                        "createdAt": current_time,
                        "updatedAt": current_time,
                        "platform": "tiktok"
                    }
                    
                    # Insert the new post
                    posts_collection.insert_one(post_document)
                    videos_added += 1
                    
                    if count >= max_videos:
                        break
                        
                except Exception as video_error:
                    browser.failed_requests += 1
                    logger.error(f"Error processing video for {username}: {str(video_error)}")
                    continue
                    
        except Exception as videos_error:
            logger.error(f"Error retrieving videos for {username}: {str(videos_error)}")
        
        browser.successful_requests += 1
        browser_accounts_processed[browser_id] += 1
        
        logger.info(f"Browser {browser_id} completed processing {username} with {len(videos)} videos (new posts added: {videos_added}, accounts processed: {browser_accounts_processed[browser_id]}/{MAX_ACCOUNTS_PER_BROWSER})")
        
        return {
            'status': 'completed',
            'username': username,
            'videos_count': len(videos),
            'videos_added': videos_added,
            'team_id': team_id
        }
        
    except Exception as e:
        logger.error(f"Browser {browser_id} error processing {username}: {str(e)}")
        browser.failed_requests += 1
        browser_accounts_processed[browser_id] += 1  # Count failed ones too
        return {
            'status': 'failed',
            'username': username,
            'error': str(e),
            'team_id': team_id
        }

async def get_teams_with_accounts() -> List[Dict[str, Any]]:
    """Retrieve all teams with their accounts from MongoDB"""
    try:
        result = creator_collection.aggregate([
            { "$unwind": "$teamsData" },
            { "$unwind": "$teamsData.accounts" },
            {
                "$group": {
                    "_id": "$teamsData.teamId",
                    "accounts": { "$addToSet": "$teamsData.accounts.name" },
                }
            },
            { "$project": { "_id": 0, "teamId": "$_id", "accounts": 1 } },
        ])

        teams = list(result)
        
        # Convert to expected format and sort accounts
        for team in teams:
            if isinstance(team["accounts"], list) and len(team["accounts"]) > 0 and isinstance(team["accounts"][0], list):
                team["accounts"] = [item for sublist in team["accounts"] for item in sublist]
            team["accounts"].sort()
            
        logger.info(f"Retrieved {len(teams)} teams with a total of {sum(len(team['accounts']) for team in teams)} accounts")
        return teams
    
    except Exception as error:
        logger.error(f"Error fetching teams with accounts: {error}")
        return []

async def run_account_processor(account_queue, results):
    """Worker that processes accounts from the queue using available browsers"""
    while account_queue:
        # Find available browser
        browser_id = None
        for i in range(NUM_BROWSERS):
            if not is_processing[i]:
                browser_id = i
                break
                
        if browser_id is None:
            # All browsers busy, wait and try again
            await asyncio.sleep(5)
            continue
            
        # Mark browser as processing
        is_processing[browser_id] = True
        
        # Get next account to process
        if not account_queue:  # Double-check queue is not empty
            is_processing[browser_id] = False
            continue
            
        task = account_queue.pop(0)
        username, team_id = task['username'], task['team_id']
        
        try:
            # Process the account
            async with browser_locks[browser_id]:
                result = await process_account(browser_id, username, team_id)
                results.append(result)
        except Exception as e:
            logger.error(f"Error in account processor for {username}: {str(e)}")
            results.append({
                'status': 'failed',
                'username': username,
                'error': str(e),
                'team_id': team_id
            })
        finally:
            # Mark browser as available
            is_processing[browser_id] = False

async def main():
    """Main function that retrieves and processes all teams and accounts"""
    start_time = time.time()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    logger.info(f"Starting TikTok scraper job for date: {today_str}")
    
    # Start browser health check tasks
    health_check_tasks = []
    for browser_id in range(NUM_BROWSERS):
        task = asyncio.create_task(check_browser_health(browser_id))
        health_check_tasks.append(task)
    
    # Get all teams and accounts
    teams = await get_teams_with_accounts()
    
    if not teams:
        logger.warning("No teams or accounts found to process")
        return
    
    # Prepare account queue
    account_queue = []
    for team in teams:
        team_id = team['teamId']
        for username in team['accounts']:
            account_queue.append({
                'username': username,
                'team_id': team_id
            })
    
    total_accounts = len(account_queue)
    logger.info(f"Prepared to process {total_accounts} accounts across {len(teams)} teams")
    
    # Create processor tasks based on number of browsers
    results = []
    processor_tasks = []
    for _ in range(NUM_BROWSERS):
        task = asyncio.create_task(run_account_processor(account_queue, results))
        processor_tasks.append(task)
    
    # Wait for all accounts to be processed
    await asyncio.gather(*processor_tasks)
    
    # Summarize results
    completed = sum(1 for r in results if r['status'] == 'completed')
    failed = sum(1 for r in results if r['status'] == 'failed')
    total_videos = sum(r.get('videos_count', 0) for r in results)
    new_posts = sum(r.get('videos_added', 0) for r in results)
    
    logger.info(f"Job completed in {time.time() - start_time:.2f} seconds")
    logger.info(f"Processed {len(results)}/{total_accounts} accounts")
    logger.info(f"Completed: {completed}, Failed: {failed}")
    logger.info(f"Total videos found: {total_videos}")
    logger.info(f"New posts added: {new_posts}")
    
    # Clean up browsers
    for browser_id in range(NUM_BROWSERS):
        if browsers[browser_id]:
            try:
                await browsers[browser_id].__aexit__(None, None, None)
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) shut down gracefully")
            except Exception as e:
                logger.error(f"Error shutting down browser {browser_id}: {str(e)}")
    
    # Cancel health check tasks
    for task in health_check_tasks:
        task.cancel()
    
    logger.info(f"TikTok scraper job for {today_str} completed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TikTok Scraper")
    parser.add_argument("--mongo-uri", help="MongoDB connection URI")
    parser.add_argument("--db-name", help="Database name")
    parser.add_argument("--browsers", type=int, help="Number of browser instances to use")
    parser.add_argument("--accounts-per-browser", type=int, help="Max accounts per browser before rotation")
    parser.add_argument("--headless", type=bool, help="Run browsers in headless mode")
    
    args = parser.parse_args()
    
    # Override config with command line arguments if provided
    if args.mongo_uri:
        MONGO_URI = args.mongo_uri
    if args.db_name:
        DB_NAME = args.db_name
    if args.browsers:
        NUM_BROWSERS = args.browsers
        browsers = [None] * NUM_BROWSERS
        is_processing = [False] * NUM_BROWSERS
        browser_locks = [asyncio.Lock() for _ in range(NUM_BROWSERS)]
        browser_uuids = [str(uuid.uuid4()) for _ in range(NUM_BROWSERS)]
        browser_accounts_processed = [0] * NUM_BROWSERS
    if args.accounts_per_browser:
        MAX_ACCOUNTS_PER_BROWSER = args.accounts_per_browser
    if args.headless is not None:
        HEADLESS = args.headless
    
    # Run the main async function
    asyncio.run(main())



