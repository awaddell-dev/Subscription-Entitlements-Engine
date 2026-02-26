import unittest
from unittest.mock import Mock
from datetime import datetime

from membership_perks_engine.membership import Membership


class FakeClock:
    def __init__(self, dt: datetime):
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


class TestMembershipWithMocking(unittest.TestCase):

    def test_sync_with_billing_updates_tier_and_perks(self):
        clock = FakeClock(datetime(2025, 5, 1, 9, 0, 0))
        member = Membership("003", "Bronze", clock=clock)
        self.assertEqual(member.perks_available, 1)

        billing = Mock()
        billing.get_member_tier.return_value = "Gold"

        member.sync_with_billing(billing)

        self.assertEqual(member.tier, "Gold")
        self.assertEqual(member.perks_available, 4)  # Gold monthly perks
        billing.get_member_tier.assert_called_once_with("003")

    def test_notify_calls_notifier(self):
        clock = FakeClock(datetime(2025, 5, 1, 9, 0, 0))
        member = Membership("001", "Silver", clock=clock)

        notifier = Mock()
        member.notify(notifier, "Welcome", "You are enrolled.")
        notifier.send.assert_called_once_with("001", "Welcome", "You are enrolled.")


if __name__ == "__main__":
    unittest.main()
