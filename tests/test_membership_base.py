import unittest
from datetime import datetime

from subscription_entitlements_engine.membership import (
    Membership,
    InactiveMemberError,
    NoPerksAvailableError,
)


class FakeClock:
    def __init__(self, dt: datetime):
        self._dt = dt

    def now(self) -> datetime:
        return self._dt

    def set(self, dt: datetime) -> None:
        self._dt = dt


class TestMembershipCore(unittest.TestCase):
    def test_bronze_starts_with_1_perk(self):
        clock = FakeClock(datetime(2025, 5, 1, 10, 0, 0))
        bronze = Membership("001", "Bronze", clock=clock)
        self.assertEqual(bronze.perks_available, 1)

        bronze.use_perk()
        self.assertEqual(bronze.perks_available, 0)

        with self.assertRaises(NoPerksAvailableError):
            bronze.use_perk()

    def test_inactive_member_cannot_use_perks(self):
        clock = FakeClock(datetime(2025, 5, 1, 10, 0, 0))
        gold = Membership("003", "Gold", is_active=False, clock=clock)

        with self.assertRaises(InactiveMemberError):
            gold.use_perk()

    def test_silver_month_refresh_resets_to_2_no_rollover(self):
        clock = FakeClock(datetime(2025, 1, 15, 9, 0, 0))
        silver = Membership("002", "Silver", clock=clock)

        silver.use_perk()  # 2 -> 1
        self.assertEqual(silver.perks_available, 1)

        # Advance to next month: auto-refresh should happen on next action
        clock.set(datetime(2025, 2, 1, 9, 0, 0))
        silver.use_perk()  # triggers refresh then uses one perk

        # Fresh month starts with 2, then uses 1 => 1 remaining
        self.assertEqual(silver.perks_available, 1)
        self.assertEqual(silver.perks_used, 1)

    def test_gold_rollover_unused_capped(self):
        clock = FakeClock(datetime(2025, 5, 1, 9, 0, 0))
        gold = Membership("003", "Gold", clock=clock)  # starts with 4

        gold.use_perk()  # now 3 unused at end-of-month scenario
        self.assertEqual(gold.perks_available, 3)

        # Jump month
        clock.set(datetime(2025, 6, 1, 9, 0, 0))

        # First action in new month triggers refresh:
        # new = 4 + unused(3) = 7, then use one => 6
        gold.use_perk()
        self.assertEqual(gold.perks_available, 6)

    def test_unknown_tier_has_zero_perks(self):
        clock = FakeClock(datetime(2025, 5, 1, 9, 0, 0))
        unknown = Membership("009", "Platinum", clock=clock)
        self.assertEqual(unknown.perks_available, 0)

        with self.assertRaises(NoPerksAvailableError):
            unknown.use_perk()


if __name__ == "__main__":
    unittest.main()
