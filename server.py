if __name__ == "__main__":
    import os
    num_workers = int(os.getenv("NUM_WORKERS", 2))
    if num_workers <= 1:
        num_workers = 1
    listen_port = int(os.getenv("LISTEN_PORT", 8000))
    if listen_port <= 0:
        listen_port = 8000

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=listen_port, workers=num_workers)
