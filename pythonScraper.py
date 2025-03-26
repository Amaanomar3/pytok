import asyncio
from quart import Quart, request, jsonify
import uuid
import logging
from collections import deque
import sys
import time
from pytok.tiktok import PyTok


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Quart(__name__)

# Number of parallel browsers to run
NUM_BROWSERS = 2

# Maximum accounts per browser before rotation
MAX_ACCOUNTS_PER_BROWSER = 20

# Global state
request_queue = deque()
processing_status = {}
browsers = [None] * NUM_BROWSERS
is_processing = [False] * NUM_BROWSERS
browser_locks = [asyncio.Lock() for _ in range(NUM_BROWSERS)]
queue_lock = asyncio.Lock()  # Single lock for queue access
browser_uuids = [str(uuid.uuid4()) for _ in range(NUM_BROWSERS)]  # Unique IDs for each browser
browser_accounts_processed = [0] * NUM_BROWSERS  # Counter for accounts processed by each browser

# Initialize a browser with better error handling
async def get_browser(browser_id):
    global browsers, browser_accounts_processed
    try:
        # Check if browser needs rotation (processed too many accounts)
        if browsers[browser_id] is not None and browser_accounts_processed[browser_id] >= MAX_ACCOUNTS_PER_BROWSER:
            logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) has processed {browser_accounts_processed[browser_id]} accounts, rotating...")
            try:
                # Close the existing browser
                await browsers[browser_id].__aexit__(None, None, None)
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) was closed for rotation")
            except Exception as close_err:
                logger.error(f"Error closing browser {browser_id} during rotation: {str(close_err)}")
            finally:
                # Reset the browser reference and generate new UUID
                browsers[browser_id] = None
                browser_uuids[browser_id] = str(uuid.uuid4())
                browser_accounts_processed[browser_id] = 0
                
        if browsers[browser_id] is None:
            browser_uuid = browser_uuids[browser_id]
            logger.info(f"Creating new browser instance for browser_id {browser_id}, UUID: {browser_uuid}")
            browser = PyTok(
                headless=True,
                browser="chromium",
                logging_level=logging.INFO,
                request_delay=1,
                manual_captcha_solves=False,
                instance_id=browser_uuid  # Pass the UUID to PyTok for tracking
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
        # Make sure we don't leave it in a processing state
        is_processing[browser_id] = False
        # Reset the browser reference so we'll try again
        browsers[browser_id] = None
        raise

# Continuous loop for each browser to pull and process from queue
async def browser_worker(browser_id):
    """Continuous worker that pulls from queue when available"""
    logger.info(f"Starting browser worker {browser_id}")
    while True:
        # Check if this browser is marked as processing
        if is_processing[browser_id]:
            logger.info(f"Browser {browser_id} is already processing, waiting...")
            await asyncio.sleep(5)
            continue
            
        # Try to acquire the browser lock
        async with browser_locks[browser_id]:
            # Double-check after acquiring lock
            if is_processing[browser_id]:
                continue  # Skip this iteration
                
            # Try to get a browser instance
            try:
                browser = await get_browser(browser_id)
                browser_uuid = browser_uuids[browser_id]
                
                # Check if there's a job in the queue
                job = None
                async with queue_lock:
                    if request_queue:
                        job = request_queue.popleft()
                        is_processing[browser_id] = True
                        logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) pulled job from queue, {len(request_queue)} remaining")
                    else:
                        # No jobs, wait before checking again
                        logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) found empty queue, waiting...")
                        # Release locks and sleep outside the lock blocks
                
                if job:
                    username = job['username']
                    job_id = job['job_id']
                    
                    # Update status to processing
                    async with queue_lock:
                        processing_status[job_id]['status'] = 'processing'
                        processing_status[job_id]['browser_id'] = browser_id
                        processing_status[job_id]['browser_uuid'] = browser_uuid
                        processing_status[job_id]['processing_started'] = time.time()
                    
                    logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) processing job {job_id} for username {username}")
                    browser.request_count += 1
                    
                    try:
                        # Process the request
                        user = browser.user(username=username)
                        user_data = await user.info()

                        videos = []
                        count = 0
                        max_videos = 10000
                        processed_video_ids = set()
                        
                        try:
                            async for video in user.videos():
                                try:
                                    video_data = await video.info()
                                    # Check if we've already processed this video ID
                                    if video_data.get('id') in processed_video_ids:
                                        continue
                                    # Add the video ID to our set of processed IDs
                                    processed_video_ids.add(video_data.get('id'))
                                    videos.append(video_data)
                                    count += 1
                                    if count >= max_videos:
                                        break
                                except Exception as video_error:
                                    browser.failed_requests += 1
                                    logger.error(f"Error processing individual video: {str(video_error)}")
                                    # Continue with next video instead of failing the entire job
                                    continue
                        except Exception as videos_error:
                            logger.error(f"Error retrieving videos for {username}: {str(videos_error)}")
                            # Continue with any videos that were successfully retrieved
                        
                        # Update status after processing, even if only partial success
                        async with queue_lock:
                            processing_status[job_id] = {
                                'status': 'completed',
                                'user': username,
                                'browser_id': browser_id,
                                'browser_uuid': browser_uuid,
                                'videos': videos,
                                'video_count': len(videos),
                                'completed_at': time.time()
                            }
                        browser.successful_requests += 1
                        # Increment the accounts processed counter for this browser
                        browser_accounts_processed[browser_id] += 1
                        logger.info(f"Browser {browser_id} (UUID: {browser_uuid}) completed job {job_id} for {username} with {len(videos)} videos (accounts processed: {browser_accounts_processed[browser_id]}/{MAX_ACCOUNTS_PER_BROWSER})")
                        
                    except Exception as e:
                        browser.failed_requests += 1
                        logger.error(f"Browser {browser_id} (UUID: {browser_uuid}) error processing {username}: {str(e)}")
                        async with queue_lock:
                            processing_status[job_id]['status'] = 'failed'
                            processing_status[job_id]['error'] = str(e)
                            processing_status[job_id]['failed_at'] = time.time()
                        # Even failed jobs count toward the rotation limit
                        browser_accounts_processed[browser_id] += 1
                    
                    # Mark browser as available again
                    is_processing[browser_id] = False
                    
                    # Add a small delay between requests to avoid rate limiting
                    await asyncio.sleep(2)
                else:
                    # No job found, wait before checking again
                    await asyncio.sleep(5)
            
            except Exception as e:
                logger.error(f"Browser {browser_id} worker error: {str(e)}")
                is_processing[browser_id] = False
                await asyncio.sleep(10)  # Wait longer after an error

@app.route('/tiktok/user/videos', methods=['GET'])
async def queue_tiktok_user_request():
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "Username parameter is required"}), 400
    
    # Generate job ID
    job_id = str(uuid.uuid4())[:8]
    
    # Add to queue with proper locking
    async with queue_lock:
        request_queue.append({
            'username': username,
            'job_id': job_id
        })
        
        # Initialize status
        processing_status[job_id] = {
            'status': 'queued',
            'position': len(request_queue),
            'queued_at': time.time()
        }
    
    logger.info(f"Added {username} to queue with job_id {job_id}, position {len(request_queue)}")
    
    # Wait for job to complete
    max_wait_time = 300  # 5 minutes timeout
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        async with queue_lock:
            if job_id in processing_status:
                status = processing_status[job_id]['status']
                if status == 'completed':
                    # Job is done, return the results
                    result = dict(processing_status[job_id])
                    return jsonify(result)
                elif status == 'failed':
                    # Job failed
                    error_msg = processing_status[job_id].get('error', 'Unknown error')
                    return jsonify({"error": error_msg, "status": "failed"}), 500
        
        # Wait a bit before checking again
        await asyncio.sleep(1)
    
    # If we get here, the job timed out
    return jsonify({
        'job_id': job_id,
        'status': 'timeout',
        'error': 'Job processing timed out'
    }), 504

# Add bulk processing endpoint
@app.route('/tiktok/batch/videos', methods=['POST'])
async def batch_user_videos():
    usernames = request.json.get('usernames', [])
    if not usernames:
        return jsonify({"error": "No usernames provided"}), 400
    
    job_ids = []
    # Add all usernames to the queue with proper locking
    async with queue_lock:
        for username in usernames:
            job_id = str(uuid.uuid4())[:8]
            
            # Add to queue
            request_queue.append({
                'username': username,
                'job_id': job_id
            })
            
            # Initialize status
            processing_status[job_id] = {
                'status': 'queued',
                'position': len(request_queue),
                'queued_at': time.time()
            }
            
            job_ids.append(job_id)
    
    logger.info(f"Added batch of {len(usernames)} usernames to queue")
    
    return jsonify({
        'batch_size': len(usernames),
        'job_ids': job_ids,
        'status': 'queued'
    })

@app.route('/status/<job_id>', methods=['GET'])
async def get_job_status(job_id):
    if job_id not in processing_status:
        return jsonify({"error": "Job not found"}), 404
    
    async with queue_lock:  # Protect access to processing_status
        status = dict(processing_status[job_id])  # Make a copy to avoid modification during response
    
    # If completed, return with results
    if status['status'] == 'completed':
        return jsonify(status)
    
    # If queued, update position
    if status['status'] == 'queued':
        position = 0
        async with queue_lock:  # Protect access to request_queue
            for job in request_queue:
                if job['job_id'] == job_id:
                    status['position'] = position
                    break
                position += 1
    
    return jsonify(status)

@app.route('/queue', methods=['GET'])
async def get_queue_status():
    queue_length = len(request_queue)
    browsers_status = []
    
    for i in range(NUM_BROWSERS):
        browser = browsers[i]
        browser_info = {
            'id': i,
            'uuid': browser_uuids[i],
            'active': is_processing[i],
            'initialized': browser is not None,
            'accounts_processed': browser_accounts_processed[i],
            'accounts_until_rotation': MAX_ACCOUNTS_PER_BROWSER - browser_accounts_processed[i],
            'uptime_seconds': time.time() - getattr(browser, 'created_at', time.time()) if browser else 0,
            'request_count': getattr(browser, 'request_count', 0) if browser else 0,
            'successful_requests': getattr(browser, 'successful_requests', 0) if browser else 0,
            'failed_requests': getattr(browser, 'failed_requests', 0) if browser else 0,
            'success_rate': f"{getattr(browser, 'failed_requests', 0)/(getattr(browser, 'successful_requests', 1) or 1):.2%}" if browser else "0.00%",
            'pytok_instance_id': getattr(browser, 'instance_id', 'not_initialized') if browser else 'not_initialized'
        }
        browsers_status.append(browser_info)
    
    return jsonify({
        'queue_length': queue_length,
        'browsers': browsers_status,
        'jobs_in_progress': sum(1 for status in processing_status.values() if status.get('status') == 'processing'),
        'jobs_queued': sum(1 for status in processing_status.values() if status.get('status') == 'queued'),
        'jobs_completed': sum(1 for status in processing_status.values() if status.get('status') == 'completed'),
        'jobs_failed': sum(1 for status in processing_status.values() if status.get('status') == 'failed')
    })

@app.route('/browser/<int:browser_id>', methods=['GET'])
async def get_browser_details(browser_id):
    """Get detailed information about a specific browser instance"""
    if browser_id < 0 or browser_id >= NUM_BROWSERS:
        return jsonify({"error": f"Invalid browser ID. Must be between 0 and {NUM_BROWSERS-1}"}), 400
    
    browser = browsers[browser_id]
    if browser is None:
        return jsonify({
            "id": browser_id,
            "uuid": browser_uuids[browser_id],
            "status": "not_initialized",
            "message": "Browser instance not initialized"
        })
    
    # Gather browser details
    browser_details = {
        "id": browser_id,
        "uuid": browser_uuids[browser_id],
        "status": "active" if is_processing[browser_id] else "idle",
        "pytok_instance_id": browser.instance_id,
        "accounts_processed": browser_accounts_processed[browser_id],
        "accounts_until_rotation": MAX_ACCOUNTS_PER_BROWSER - browser_accounts_processed[browser_id],
        "user_agent": getattr(browser, "_user_agent", "unknown"),
        "browser_type": getattr(browser, "_browser_type", "unknown"),
        "uptime_seconds": time.time() - browser.created_at,
        "uptime_formatted": f"{(time.time() - browser.created_at) / 60:.1f} minutes",
        "headless": getattr(browser, "_headless", None),
        "request_delay": getattr(browser, "_request_delay", None),
        "request_count": browser.request_count,
        "successful_requests": browser.successful_requests,
        "failed_requests": browser.failed_requests,
        "success_rate": f"{browser.successful_requests/(browser.request_count or 1):.2%}",
        "has_active_page": browser._page is not None,
    }
    
    # Get currently processing job if any
    if is_processing[browser_id]:
        current_jobs = []
        for job_id, status in processing_status.items():
            if status.get('status') == 'processing' and status.get('browser_id') == browser_id:
                job_info = {
                    "job_id": job_id,
                    "username": status.get('user', 'unknown'),
                    "started_at": status.get('processing_started', 0),
                    "duration": f"{(time.time() - status.get('processing_started', time.time())):.1f} seconds"
                }
                current_jobs.append(job_info)
        browser_details["current_jobs"] = current_jobs
    
    return jsonify(browser_details)

@app.route('/test/user/<username>', methods=['GET'])
async def test_user_access(username):
    """Test endpoint to directly verify PyTok user access works"""
    try:
        # Use browser 0 for testing
        browser_id = 0
        browser = await get_browser(browser_id)
        if not browser:
            return jsonify({"error": "Browser not initialized"}), 500
            
        # Try to create a user object and get info
        logger.info(f"Testing user access for {username} with browser {browser_id}")
        
        # Debugging
        logger.info(f"Browser instance ID: {browser.instance_id}")
        logger.info(f"Browser type: {browser._browser_type}")
        
        # Create user instance
        user = browser.user(username=username)
        
        # Check user instance parent
        logger.info(f"User parent instance ID: {getattr(user.parent, 'instance_id', 'unknown')}")
        
        # Get user info
        user_data = await user.info()
        
        # Return basic user info
        return jsonify({
            "status": "success",
            "username": username,
            "user_id": user.user_id,
            "sec_uid": user.sec_uid,
            "follower_count": user_data.get("followerCount", 0),
            "following_count": user_data.get("followingCount", 0),
            "video_count": user_data.get("videoCount", 0),
            "bio": user_data.get("signature", ""),
            "browser_instance_id": browser.instance_id,
            "user_parent_instance_id": getattr(user.parent, 'instance_id', 'unknown')
        })
    except Exception as e:
        logger.error(f"Error testing user access: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Browser health check
async def check_browser_health(browser_id):
    """Periodically check if browser is responsive and restart if needed"""
    while True:
        if browsers[browser_id] is not None and is_processing[browser_id]:
            try:
                # Simple health check - try to evaluate a basic JS
                await browsers[browser_id]._page.evaluate("1+1")
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) health check passed")
            except Exception as e:
                logger.error(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) health check failed: {str(e)}")
                # Reset browser status so it can be restarted
                is_processing[browser_id] = False
                # Try to close browser
                try:
                    if browsers[browser_id]:
                        await browsers[browser_id].__aexit__(None, None, None)
                except Exception as close_error:
                    logger.error(f"Error closing unhealthy browser {browser_id}: {str(close_error)}")
                finally:
                    browsers[browser_id] = None
                    # Browser will be reinitialized on next request
            
        await asyncio.sleep(60)  # Check every minute

@app.route('/browser/rotate/<int:browser_id>', methods=['POST'])
async def rotate_browser(browser_id):
    """Force rotation of a specific browser instance"""
    if browser_id < 0 or browser_id >= NUM_BROWSERS:
        return jsonify({"error": f"Invalid browser ID. Must be between 0 and {NUM_BROWSERS-1}"}), 400
    
    if is_processing[browser_id]:
        return jsonify({"error": "Cannot rotate browser while it's processing a request"}), 400
    
    async with browser_locks[browser_id]:
        old_uuid = browser_uuids[browser_id]
        try:
            if browsers[browser_id] is not None:
                await browsers[browser_id].__aexit__(None, None, None)
                logger.info(f"Browser {browser_id} (UUID: {old_uuid}) was manually rotated")
            
            browsers[browser_id] = None
            browser_uuids[browser_id] = str(uuid.uuid4())
            browser_accounts_processed[browser_id] = 0
            
            # Initialize the new browser right away
            await get_browser(browser_id)
            
            return jsonify({
                "success": True,
                "message": f"Browser {browser_id} rotated successfully",
                "old_uuid": old_uuid,
                "new_uuid": browser_uuids[browser_id]
            })
        except Exception as e:
            logger.error(f"Error rotating browser {browser_id}: {str(e)}")
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

# Clean up on exit
@app.before_serving
async def startup():
    # Generate new UUIDs for this session
    global browser_uuids, browser_accounts_processed
    browser_uuids = [str(uuid.uuid4()) for _ in range(NUM_BROWSERS)]
    browser_accounts_processed = [0] * NUM_BROWSERS
    
    # Start browser worker tasks
    for browser_id in range(NUM_BROWSERS):
        asyncio.create_task(browser_worker(browser_id))
        # Start health check tasks
        asyncio.create_task(check_browser_health(browser_id))
        
    logger.info(f"Started {NUM_BROWSERS} browser workers")

@app.after_serving
async def shutdown():
    global browsers
    for browser_id in range(NUM_BROWSERS):
        if browsers[browser_id]:
            try:
                await browsers[browser_id].__aexit__(None, None, None)
                logger.info(f"Browser {browser_id} (UUID: {browser_uuids[browser_id]}) shut down gracefully")
            except Exception as e:
                logger.error(f"Error shutting down browser {browser_id}: {str(e)}")
            finally:
                browsers[browser_id] = None
        
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)



