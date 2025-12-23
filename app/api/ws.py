from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.ws_manager import ws_manager

router = APIRouter()

@router.websocket("")
async def unified_ws(websocket: WebSocket):
    await ws_manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            resp = await ws_manager.handle_message(websocket, raw)
            if resp is not None:
                await websocket.send_json(resp)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] fatal error: {e}")
        ws_manager.disconnect(websocket)
