import asyncio
import argparse

from pytok.tiktok import PyTok

async def main(username):
    async with PyTok() as api:
        user = api.user(username=username)
        user_data = await user.info()
        print(user_data)

        videos= []
        async for video in user.videos():
            video_data = await video.info()
            print(video_data)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch TikTok user data")
    parser.add_argument("--username", type=str, required=True, help="TikTok username to fetch data for")

    args = parser.parse_args()
    asyncio.run(main(args.username))
