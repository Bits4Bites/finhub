# import asyncio
import sys

# print(f"[DEBUG] Python version: {sys.version} / Platform: {sys.platform}")
# if sys.platform.startswith("win"):
#     print("[DEBUG] Windows - switching to WindowsProactorEventLoopPolicy...")
#     asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    import os

    num_workers = int(os.getenv("NUM_WORKERS", 2))
    if num_workers <= 1:
        num_workers = 1
    if sys.platform.startswith("win"):
        num_workers = None

    listen_port = int(os.getenv("LISTEN_PORT", 8000))
    if listen_port <= 0:
        listen_port = 8000

    reload = os.getenv("RELOAD", "false").lower() == "true"
    # if sys.platform.startswith("win"):
    #     reload = True

    import uvicorn
    loop = "none" if sys.platform.startswith("win") else "auto"
    uvicorn.run("app.main:app", host="0.0.0.0", port=listen_port, workers=num_workers, reload=reload, loop=loop)
