"""
WebSocket server — broadcasts bulletin board events to the React dashboard.
Runs in its own asyncio event loop in a background thread.
"""

import asyncio
import json
import threading
import logging
from dataclasses import asdict

import websockets

from shared_state import bulletin

logger = logging.getLogger(__name__)

WS_HOST = "0.0.0.0"
WS_PORT = 8765


async def _handler(websocket):
    bulletin.register_ws_client(websocket)
    logger.info(f"Dashboard connected: {websocket.remote_address}")

    # Send full history on connect
    try:
        history = bulletin.snapshot(max_events=200)
        await websocket.send(json.dumps({"type": "history", "events": history}))

        # Keep connection alive
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        bulletin.unregister_ws_client(websocket)
        logger.info(f"Dashboard disconnected: {websocket.remote_address}")


def start_ws_server():
    """Start WebSocket server in a background thread."""
    loop = asyncio.new_event_loop()
    bulletin.set_ws_loop(loop)

    def _run():
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(
            websockets.serve(_handler, WS_HOST, WS_PORT)
        )
        logger.info(f"WebSocket server on ws://{WS_HOST}:{WS_PORT}")
        loop.run_forever()
        server.close()

    thread = threading.Thread(target=_run, daemon=True, name="ws-server")
    thread.start()
    return thread
