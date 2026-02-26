from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Protocol, Any



# ---------------------------- Exceptions ------------------------------- #

class MembershipError(Exception):
    """Base error for membership domain."""


class InactiveMemberError(MembershipError):
    """Raised when an inactive member attempts an action."""


class NoPerksAvailableError(MembershipError):
    """Raised when a member tries to use a perk but has none."""


class UnknownTierError(MembershipError):
    """Raised when a tier is invalid or unsupported."""


# ----------------------------
# Time abstraction (testability)
# ----------------------------

class Clock(Protocol):
    def now(self) -> datetime:
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now()


# ----------------------------
# External dependencies (mockable)
# ----------------------------

class BillingProvider(Protocol):
    def get_member_tier(self, member_id: str) -> str:
        ...


class Notifier(Protocol):
    def send(self, to_member_id: str, subject: str, body: str) -> None:
        ...


# ----------------------------
# Tier policy (data-driven rules)
# ----------------------------

@dataclass(frozen=True)
class TierPolicy:
    monthly_perks: int
    rollover_unused: bool = False
    rollover_cap: Optional[int] = None  # e.g., cap total perks at 8 for Gold


TIER_POLICIES: Dict[str, TierPolicy] = {
    "Bronze": TierPolicy(monthly_perks=1, rollover_unused=False),
    "Silver": TierPolicy(monthly_perks=2, rollover_unused=False),
    "Gold":   TierPolicy(monthly_perks=4, rollover_unused=True, rollover_cap=8),
}


def month_key(dt: datetime) -> str:
    """Used to detect month transitions (YYYY-MM)."""
    return f"{dt.year:04d}-{dt.month:02d}"


# ----------------------------
# Core domain model
# ----------------------------

class Membership:
    """
    Subscription perks engine:
    - tier-based monthly perks
    - optional rollover (Gold rolls unused perks, capped)
    - automatic monthly refresh based on clock
    - audit trail for actions (operational thinking)
    """

    def __init__(
        self,
        member_id: str,
        tier: str,
        is_active: bool = True,
        clock: Optional[Clock] = None,
    ):
        self.member_id = member_id
        self.tier = tier
        self.is_active = is_active
        self.clock: Clock = clock or SystemClock()

        self.perks_available: int = 0
        self.perks_used: int = 0
        self.audit_log: List[Dict[str, Any]] = []

        # Track month to enable auto-refresh
        self._current_month_key: str = month_key(self.clock.now())

        # Initialize perks for current month
        self._initialize_month()

    def _policy(self) -> TierPolicy:
        if self.tier not in TIER_POLICIES:
            return TierPolicy(monthly_perks=0, rollover_unused=False)
        return TIER_POLICIES[self.tier]

    def _log(self, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        entry = {
            "timestamp": self.clock.now(),
            "action": action,
            "member_id": self.member_id,
            "tier": self.tier,
        }
        if details:
            entry.update(details)
        self.audit_log.append(entry)

    def _initialize_month(self) -> None:
        """Set perks for the current month on first creation."""
        policy = self._policy()
        self.perks_available = policy.monthly_perks
        self.perks_used = 0
        self._log("init_month", {"perks_available": self.perks_available})

    def _refresh_if_needed(self) -> None:
        """Automatically refresh perks if we crossed into a new month."""
        now = self.clock.now()
        key = month_key(now)
        if key != self._current_month_key:
            self._refresh_for_new_month()
            self._current_month_key = key

    def _refresh_for_new_month(self) -> None:
        """Refresh perks at month boundary, applying rollover rules."""
        policy = self._policy()

        unused = self.perks_available  # perks remaining at end of month
        base = policy.monthly_perks
        rollover_add = unused if policy.rollover_unused else 0

        new_total = base + rollover_add

        if policy.rollover_cap is not None:
            new_total = min(new_total, policy.rollover_cap)

        self.perks_available = new_total
        self.perks_used = 0

        self._log(
            "month_refresh",
            {"unused_prev_month": unused, "new_perks_available": self.perks_available},
        )

    def use_perk(self) -> None:
        self._refresh_if_needed()

        if not self.is_active:
            self._log("use_perk_denied_inactive")
            raise InactiveMemberError("Member is not active. Cannot access perks.")

        if self.perks_available <= 0:
            self._log("use_perk_denied_no_perks")
            raise NoPerksAvailableError("No perks available to use.")

        self.perks_available -= 1
        self.perks_used += 1
        self._log("perk_used", {"perks_available": self.perks_available})

    def set_active(self, active: bool) -> None:
        self.is_active = active
        self._log("set_active", {"is_active": self.is_active})

    def apply_tier_change(self, new_tier: str) -> None:
        """
        Apply tier change in a reasonable, deterministic way:
        - Keep perks_used for this month
        - Recompute remaining perks as: monthly_perks - perks_used (min 0)
        - No retro rollover mid-month
        """
        self._refresh_if_needed()

        old_tier = self.tier
        self.tier = new_tier
        policy = self._policy()

        remaining = max(policy.monthly_perks - self.perks_used, 0)
        self.perks_available = remaining

        self._log("tier_changed", {"old_tier": old_tier, "new_tier": new_tier, "perks_available": remaining})

    def sync_with_billing(self, billing: BillingProvider) -> None:
        """Pull tier from a billing provider (Stripe-like)."""
        new_tier = billing.get_member_tier(self.member_id)
        self.apply_tier_change(new_tier)

    def notify(self, notifier: Notifier, subject: str, body: str) -> None:
        notifier.send(self.member_id, subject, body)
        self._log("notified", {"subject": subject})


# ----------------------------
# Service layer (makes it feel “real”)
# ----------------------------

class MembershipService:
    """Manages many memberships like a small backend service would."""

    def __init__(self):
        self._members: Dict[str, Membership] = {}

    def add_member(self, membership: Membership) -> None:
        self._members[membership.member_id] = membership

    def get(self, member_id: str) -> Membership:
        if member_id not in self._members:
            raise KeyError(f"Member {member_id} not found")
        return self._members[member_id]

    def use_perk(self, member_id: str) -> None:
        self.get(member_id).use_perk()

    def sync_all(self, billing: BillingProvider) -> None:
        for m in self._members.values():
            m.sync_with_billing(billing)
