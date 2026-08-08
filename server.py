import sys

if __name__ == "__main__":
    import os

    listen_port = int(os.getenv("LISTEN_PORT", 8000))
    if listen_port <= 0:
        listen_port = 8000

    reload = os.getenv("RELOAD", "false").lower() == "true"

    import uvicorn

    loop = "none" if sys.platform.startswith("win") else "auto"
    uvicorn.run("app.main:app", host="0.0.0.0", port=listen_port, reload=reload, loop=loop)
