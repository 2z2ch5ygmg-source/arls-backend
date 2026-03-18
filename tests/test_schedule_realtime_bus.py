from __future__ import annotations

import unittest

from app.realtime import ScheduleEventBus


class ScheduleEventBusTest(unittest.TestCase):
    def test_site_scoped_subscription_receives_blank_site_event(self) -> None:
        bus = ScheduleEventBus(enable_database_transport=False)
        subscription = bus.subscribe(
            tenant_id="tenant-1",
            month="2026-03",
            site_code="R692",
        )
        try:
            bus.publish(
                {
                    "type": "schedule_changed",
                    "tenant_id": "tenant-1",
                    "month": "2026-03",
                    "site_code": "",
                    "event_uid": "evt-1",
                }
            )
            received = subscription.queue.get(timeout=1)
        finally:
            bus.unsubscribe(subscription.id)

        self.assertEqual(received["event_uid"], "evt-1")

    def test_site_scoped_subscription_still_filters_other_site(self) -> None:
        bus = ScheduleEventBus(enable_database_transport=False)
        subscription = bus.subscribe(
            tenant_id="tenant-1",
            month="2026-03",
            site_code="R692",
        )
        try:
            bus.publish(
                {
                    "type": "schedule_changed",
                    "tenant_id": "tenant-1",
                    "month": "2026-03",
                    "site_code": "R738",
                    "event_uid": "evt-2",
                }
            )
            self.assertTrue(subscription.queue.empty())
        finally:
            bus.unsubscribe(subscription.id)

    def test_handle_remote_event_delivers_blank_site_payload_to_site_subscription(self) -> None:
        bus = ScheduleEventBus(enable_database_transport=False)
        subscription = bus.subscribe(
            tenant_id="tenant-1",
            month="2026-03",
            site_code="R692",
        )
        try:
            bus.handle_remote_event(
                {
                    "type": "schedule_changed",
                    "tenant_id": "tenant-1",
                    "month": "2026-03",
                    "site_code": "",
                    "event_uid": "evt-3",
                    "_origin_instance": "remote-instance",
                }
            )
            received = subscription.queue.get(timeout=1)
        finally:
            bus.unsubscribe(subscription.id)

        self.assertEqual(received["event_uid"], "evt-3")

    def test_handle_remote_event_ignores_same_instance_origin(self) -> None:
        bus = ScheduleEventBus(enable_database_transport=False)
        subscription = bus.subscribe(
            tenant_id="tenant-1",
            month="2026-03",
            site_code="R692",
        )
        try:
            bus.handle_remote_event(
                {
                    "type": "schedule_changed",
                    "tenant_id": "tenant-1",
                    "month": "2026-03",
                    "site_code": "R692",
                    "event_uid": "evt-4",
                    "_origin_instance": bus._instance_id,
                }
            )
            self.assertTrue(subscription.queue.empty())
        finally:
            bus.unsubscribe(subscription.id)


if __name__ == "__main__":
    unittest.main()
