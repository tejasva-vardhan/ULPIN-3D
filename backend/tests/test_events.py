"""In-process activity feed. Does not need PostGIS."""

import asyncio
import json
import unittest

from app import events


class EventBrokerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        events._subscribers.clear()
        events._history.clear()
        events._main_loop = None

    async def test_new_tab_replays_recent_history(self):
        await events.publish("site.created", {"name": "Kothrud"})
        gen = events.subscribe()
        try:
            first = await asyncio.wait_for(gen.__anext__(), 1)
        finally:
            await gen.aclose()
        self.assertEqual(first["type"], "site.created")
        self.assertEqual(first["payload"]["name"], "Kothrud")
        self.assertIn("ts", first)

    async def test_live_subscriber_receives_publish(self):
        received = []

        async def consume():
            async for event in events.subscribe():
                received.append(event)
                break

        task = asyncio.create_task(consume())
        for _ in range(50):
            if events._subscribers:
                break
            await asyncio.sleep(0)
        self.assertTrue(events._subscribers)
        await events.publish("demo.seeded", {"spatial_units": 25})
        await asyncio.wait_for(task, 1)
        self.assertEqual(received[0]["type"], "demo.seeded")
        self.assertEqual(received[0]["payload"]["spatial_units"], 25)

    def test_sse_frame_is_one_eventsource_message(self):
        frame = events.sse_pack({"type": "validation.run", "payload": {"error_count": 4}, "ts": 1})
        self.assertTrue(frame.startswith("data: "))
        self.assertTrue(frame.endswith("\n\n"))
        body = json.loads(frame[len("data: "):-2])
        self.assertEqual(body["type"], "validation.run")

    def test_emit_never_raises_without_a_loop(self):
        events.emit("unit.issued", {"local_code": "F05-U501"})


if __name__ == "__main__":
    unittest.main()
