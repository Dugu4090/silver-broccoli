from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, SessionLocal
from app.deps import get_current_user
from app.models import Room, RoomMessage, User
from app.core.security import decode
from app.redis_client import redis
import json
import asyncio

router = APIRouter()


@router.post("/{name}")
async def ensure_room(name: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Room).where(Room.name == name))
    r = res.scalar_one_or_none()
    if not r:
        r = Room(name=name, created_by=user.id)
        db.add(r); await db.commit(); await db.refresh(r)
    return {"id": r.id, "name": r.name}


@router.get("/{room_id}/messages")
async def history(room_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(RoomMessage).where(RoomMessage.room_id == room_id)
        .order_by(RoomMessage.id.desc()).limit(100)
    )
    rows = list(reversed(list(res.scalars())))
    return [{"id": m.id, "user_email": m.user_email, "text": m.text,
             "created_at": m.created_at.isoformat()} for m in rows]


@router.websocket("/ws/{room_id}")
async def ws(websocket: WebSocket, room_id: int, token: str = Query(...)):
    try:
        payload = decode(token)
    except Exception:
        await websocket.close(code=4401)
        return
    if payload.get("type") != "access":
        await websocket.close(code=4401)
        return
    email = payload["sub"]
    await websocket.accept()
    pubsub = redis.pubsub()
    channel = f"room:{room_id}"
    await pubsub.subscribe(channel)

    async def reader():
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                await websocket.send_text(msg["data"])

    task = asyncio.create_task(reader())
    try:
        while True:
            text = await websocket.receive_text()
            async with SessionLocal() as db:
                u = (await db.execute(select(User).where(User.email == email))).scalar_one()
                m = RoomMessage(room_id=room_id, user_id=u.id, user_email=email, text=text)
                db.add(m); await db.commit(); await db.refresh(m)
            payload = json.dumps({"id": m.id, "user_email": email, "text": text,
                                  "created_at": m.created_at.isoformat()})
            await redis.publish(channel, payload)
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        await pubsub.unsubscribe(channel)
