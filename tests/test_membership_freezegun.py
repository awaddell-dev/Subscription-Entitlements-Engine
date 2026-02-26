import unittest
from freezegun import freeze_time

from subscription_entitlements_engine.membership import Membership


class TestMembershipWithFreezegun(unittest.TestCase):

    @freeze_time("2025-05-01 10:00:00")
    def test_gold_rollover_freezegun(self):
        gold = Membership("003", "Gold")  # starts with 4
        gold.use_perk()  # leaves 3

        # Move time to next month; next action triggers refresh automatically
        with freeze_time("2025-06-01 10:00:00"):
            gold.use_perk()
            # refreshed: 4 + 3 = 7, then used 1 => 6
            self.assertEqual(gold.perks_available, 6)
            self.assertEqual(gold.perks_used, 1)

    @freeze_time("2025-01-20 10:00:00")
    def test_silver_reset_on_new_month_freezegun(self):
        silver = Membership("007", "Silver")  # starts 2
        silver.use_perk()  # leaves 1

        with freeze_time("2025-02-01 10:00:00"):
            silver.use_perk()
            # refresh sets to 2, then uses 1 => 1
            self.assertEqual(silver.perks_available, 1)
            self.assertEqual(silver.perks_used, 1)


if __name__ == "__main__":
    unittest.main()
