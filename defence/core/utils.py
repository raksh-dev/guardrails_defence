import time
import asyncio
async def char_streamer(file_path: str):
    with open(file_path, "r") as f:
        for line in f:
            yield line
            await asyncio.sleep(0.05)
