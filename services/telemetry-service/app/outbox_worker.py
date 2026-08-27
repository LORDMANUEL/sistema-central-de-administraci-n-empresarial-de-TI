import asyncio,json
from datetime import UTC,datetime
import nats
from nats.js.errors import NotFoundError
from sqlalchemy import select
from .config import get_settings
from .database import build_engine,build_session_factory
from .models import OutboxEvent
async def main():
 s=get_settings();engine=build_engine(s.database_url);factory=build_session_factory(engine);nc=await nats.connect(s.nats_url,connect_timeout=3,max_reconnect_attempts=-1);js=nc.jetstream()
 try:
  try:await js.stream_info(s.nats_stream)
  except NotFoundError:await js.add_stream(name=s.nats_stream,subjects=["guardian.>"])
  while True:
   with factory() as session:
    rows=session.execute(select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at).limit(100)).scalars().all()
    for row in rows:
     try:
      envelope={"schema_version":1,"event_id":str(row.event_id),"type":row.subject.removeprefix("guardian."),"aggregate_id":row.aggregate_id,"occurred_at":row.created_at.isoformat(),"data":row.payload};await js.publish(row.subject,json.dumps(envelope,separators=(",",":"),sort_keys=True).encode(),headers={"Nats-Msg-Id":str(row.event_id)});row.published_at=datetime.now(UTC);row.last_error=None
     except Exception as exc:row.attempts+=1;row.last_error=str(exc)[:512]
    session.commit()
   await asyncio.sleep(1 if rows else 2)
 finally:await nc.drain();engine.dispose()
if __name__=="__main__":asyncio.run(main())
