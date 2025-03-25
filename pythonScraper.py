import asyncio
import argparse

from pytok.tiktok import PyTok

async def main(username):
    async with PyTok(headless=True) as api:
        user = api.user(username=username)
        user_data = await user.info()
        # print(user_data)

        videos = []
        async for video in user.videos():
            video_data = await video.info()
            # if video  exists in list, skip
            if video_data in videos:
                continue
            videos.append(video_data)
            # print(video_data)
        
        print(len(videos))
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch TikTok user data")
    parser.add_argument("--username", type=str, required=True, help="TikTok username to fetch data for")

    args = parser.parse_args()
    asyncio.run(main(args.username))



