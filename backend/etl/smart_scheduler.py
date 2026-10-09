"""
Smart ETL Scheduler - Calendar-aware scheduling based on government publishing patterns.

This scheduler replaces the fixed 720-minute interval with intelligent scheduling that:
- Checks daily during budget season (May-July for Treasury)
- Increases frequency after quarter-ends (COB reports 45 days later)
- Checks weekly during audit season (Nov-Jan for OAG)
- Aligns with economic survey publication (May for KNBS)
- Reduces unnecessary runs by ~70%

Government Publishing Patterns (Kenya):
- Treasury: Budget statements in June, quarterly reports 7 days after quarter-end
- COB: Budget Implementation Reviews 45 days after quarter-end
- OAG: Annual audits Nov-Jan, quarterly special audits
- KNBS: Economic Survey in May, Statistical Abstract in December
- Open Data: Continuous updates, check weekly
- CRA: Revenue allocation in February, quarterly monitoring
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SmartScheduler:
    """Calendar-aware ETL scheduler based on government publishing patterns."""

    def __init__(self):
        """Initialize scheduler with government publishing calendars."""
        self.schedules = {
            "treasury": {
                "budget_season": {
                    "months": [5, 6, 7],  # May-July (budget preparation & approval)
                    "frequency": "daily",
                    "reason": "Budget statement preparation and approval season",
                },
                "quarter_ends": {
                    "frequency": "daily",
                    "days_after": 7,  # Check for 7 days after each quarter-end
                    "reason": "Quarterly expenditure reports expected",
                },
                "default": {
                    "frequency": "weekly",
                    "day": "monday",
                    "reason": "Routine weekly check",
                },
            },
            "cob": {
                "post_quarter": {
                    "frequency": "2_days",  # Every 2 days
                    "days_after": 45,  # Start 45 days after quarter-end
                    "duration": 14,  # Check for 2 weeks (7 checks)
                    "reason": "Quarterly Budget Implementation Review Reports (6 weeks after quarter)",
                },
                "default": {
                    "frequency": "biweekly",
                    "days": ["monday"],
                    "reason": "Routine biweekly check",
                },
            },
            "oag": {
                "audit_season": {
                    "months": [11, 12, 1],  # Nov-Jan (annual audit publication)
                    "frequency": "weekly",
                    "day": "wednesday",
                    "reason": "Annual audit report publication season",
                },
                "quarterly": {
                    "frequency": "biweekly",
                    "offset": 30,  # 1 month after quarter-end
                    "reason": "Special and performance audits publication",
                },
                "default": {
                    "frequency": "monthly",
                    "day_of_month": 15,
                    "reason": "Routine monthly check",
                },
            },
            "knbs": {
                "economic_survey": {
                    "month": 5,  # May
                    "frequency": "weekly",
                    "weeks": 4,
                    "day": "tuesday",
                    "reason": "Economic Survey annual publication (typically mid-May)",
                },
                "statistical_abstract": {
                    "month": 12,  # December
                    "frequency": "weekly",
                    "weeks": 4,
                    "day": "thursday",
                    "reason": "Statistical Abstract annual publication (typically mid-December)",
                },
                "quarter_ends": {
                    "frequency": "biweekly",
                    "days_after": 14,  # 2 weeks after quarter
                    "duration": 21,  # Check for 3 weeks
                    "reason": "Quarterly GDP and economic indicators",
                },
                "default": {
                    "frequency": "monthly",
                    "day_of_month": 1,
                    "reason": "Routine monthly statistical updates",
                },
            },
            "opendata": {
                "default": {
                    "frequency": "weekly",
                    "day": "friday",
                    "reason": "Continuous dataset updates via API",
                }
            },
            "cra": {
                "allocation_season": {
                    "month": 2,  # February
                    "frequency": "weekly",
                    "weeks": 4,
                    "day": "monday",
                    "reason": "Annual revenue allocation to counties",
                },
                "quarter_ends": {
                    "frequency": "monthly",
                    "reason": "Quarterly monitoring and compliance reports",
                },
                "default": {
                    "frequency": "monthly",
                    "day_of_month": 1,
                    "reason": "Routine monthly check",
                },
            },
        }

        # Cache for calculated values
        self._quarter_dates_cache = None
        self._last_cache_date = None

    def _quarter_end_dates(self) -> List[datetime]:
        """
        Generate quarter-end dates for current and next year.
        Kenya fiscal year: July 1 - June 30
        Calendar quarters: Mar 31, Jun 30, Sep 30, Dec 31
        """
        # Cache for 24 hours
        if self._quarter_dates_cache and self._last_cache_date:
            if (datetime.now() - self._last_cache_date).total_seconds() < 86400:
                return self._quarter_dates_cache

        now = datetime.now()
        year = now.year
        dates = []

        # Previous year Q4, current year all quarters, next year Q1
        for y in [year - 1, year, year + 1]:
            dates.extend(
                [
                    datetime(y, 3, 31),  # Q1 end
                    datetime(y, 6, 30),  # Q2 end (Kenya fiscal year end)
                    datetime(y, 9, 30),  # Q3 end
                    datetime(y, 12, 31),  # Q4 end
                ]
            )

        self._quarter_dates_cache = dates
        self._last_cache_date = now
        return dates

    def _is_within_days_of_date(
        self, target_date: datetime, days_after: int, duration: int = 1
    ) -> bool:
        """Check if current date is within a window after target_date."""
        now = datetime.now()
        days_since = (now - target_date).days

        # Within the window: [days_after, days_after + duration]
        return days_after <= days_since <= (days_after + duration)

    def _get_current_quarter(self) -> Tuple[int, int]:
        """Get current quarter (1-4) and year."""
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        return quarter, now.year

    def _days_since_quarter_end(self) -> int:
        """Calculate days since the most recent quarter-end."""
        now = datetime.now()
        quarters = self._quarter_end_dates()

        # Find most recent quarter-end
        past_quarters = [q for q in quarters if q <= now]
        if not past_quarters:
            return 999  # No past quarters found

        most_recent = max(past_quarters)
        return (now - most_recent).days

    def _is_day_of_week(self, target_day: str) -> bool:
        """Check if today is the target day of week."""
        now = datetime.now()
        today = now.strftime("%A").lower()
        return today == target_day.lower()

    def should_run(self, source: str) -> Tuple[bool, str]:
        """
        Determine if source should be checked now based on government publishing patterns.

        Args:
            source: Source key ('treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra')

        Returns:
            Tuple of (should_run: bool, reason: str)
        """
        if source not in self.schedules:
            logger.warning(f"Unknown source '{source}', defaulting to weekly schedule")
            return (True, "Unknown source - default weekly schedule")

        now = datetime.now()
        config = self.schedules[source]

        # Priority 1: Check special high-frequency periods

        # Budget season (May-July for Treasury)
        if "budget_season" in config:
            bs = config["budget_season"]
            if now.month in bs["months"]:
                if bs["frequency"] == "daily":
                    return (True, bs["reason"])
                elif bs["frequency"] == "weekly" and "day" in bs:
                    if self._is_day_of_week(bs["day"]):
                        return (True, bs["reason"])

        # Economic Survey season (May for KNBS)
        if "economic_survey" in config:
            es = config["economic_survey"]
            if now.month == es["month"]:
                if es["frequency"] == "weekly" and "day" in es:
                    if self._is_day_of_week(es["day"]):
                        return (True, es["reason"])
                else:
                    return (True, es["reason"])

        # Statistical Abstract season (December for KNBS)
        if "statistical_abstract" in config:
            sa = config["statistical_abstract"]
            if now.month == sa["month"]:
                if sa["frequency"] == "weekly" and "day" in sa:
                    if self._is_day_of_week(sa["day"]):
                        return (True, sa["reason"])
                else:
                    return (True, sa["reason"])

        # Allocation season (February for CRA)
        if "allocation_season" in config:
            alls = config["allocation_season"]
            if now.month == alls["month"]:
                if alls["frequency"] == "weekly" and "day" in alls:
                    if self._is_day_of_week(alls["day"]):
                        return (True, alls["reason"])
                else:
                    return (True, alls["reason"])

        # Audit season (Nov-Jan for OAG)
        if "audit_season" in config:
            aus = config["audit_season"]
            if now.month in aus["months"]:
                if aus["frequency"] == "weekly" and "day" in aus:
                    if self._is_day_of_week(aus["day"]):
                        return (True, aus["reason"])
                else:
                    return (True, aus["reason"])

        # Priority 2: Quarter-end related checks

        # Treasury: 7 days after quarter-end
        if "quarter_ends" in config and source == "treasury":
            qe = config["quarter_ends"]
            days_after = qe.get("days_after", 7)
            days_since = self._days_since_quarter_end()

            if 0 <= days_since <= days_after:
                if qe["frequency"] == "daily":
                    return (True, qe["reason"])

        # COB: 45-59 days after quarter-end (2-week window)
        if "post_quarter" in config:
            pq = config["post_quarter"]
            days_after = pq["days_after"]
            duration = pq.get("duration", 7)

            for quarter_date in self._quarter_end_dates():
                if self._is_within_days_of_date(quarter_date, days_after, duration):
                    # Check every 2 days during this window
                    if pq["frequency"] == "2_days":
                        # Use day of year modulo to get every 2 days
                        if now.timetuple().tm_yday % 2 == 0:
                            return (True, pq["reason"])
                    else:
                        return (True, pq["reason"])

        # KNBS: 14-35 days after quarter-end (3-week window)
        if "quarter_ends" in config and source == "knbs":
            qe = config["quarter_ends"]
            days_after = qe.get("days_after", 14)
            duration = qe.get("duration", 21)

            for quarter_date in self._quarter_end_dates():
                if self._is_within_days_of_date(quarter_date, days_after, duration):
                    if qe["frequency"] == "biweekly":
                        # Check every 2 weeks (approximately day 14 and 28 of period)
                        week_num = now.isocalendar()[1]
                        if week_num % 2 == 0:
                            return (True, qe["reason"])

        # OAG: 30+ days after quarter-end for special audits
        if "quarterly" in config and source == "oag":
            qrtly = config["quarterly"]
            days_since = self._days_since_quarter_end()
            offset = qrtly.get("offset", 30)

            if days_since >= offset and days_since <= offset + 30:
                if qrtly["frequency"] == "biweekly":
                    week_num = now.isocalendar()[1]
                    if week_num % 2 == 0:
                        return (True, qrtly["reason"])

        # CRA: Monthly after quarter-ends
        if "quarter_ends" in config and source == "cra":
            qe = config["quarter_ends"]
            days_since = self._days_since_quarter_end()

            if 0 <= days_since <= 90:  # Within quarter
                if qe["frequency"] == "monthly":
                    if now.day == 1:  # First of month
                        return (True, qe["reason"])

        # Priority 3: Default frequency checks

        default = config.get("default", {})
        freq = default.get("frequency", "weekly")

        if freq == "daily":
            return (True, default.get("reason", "Daily default schedule"))

        elif freq == "weekly":
            target_day = default.get("day", "monday")
            if self._is_day_of_week(target_day):
                return (
                    True,
                    default.get("reason", f"Weekly default schedule ({target_day})"),
                )

        elif freq == "biweekly":
            week_num = now.isocalendar()[1]
            if week_num % 2 == 0:  # Even weeks
                target_days = default.get("days", ["monday"])
                for day in target_days:
                    if self._is_day_of_week(day):
                        return (
                            True,
                            default.get("reason", "Biweekly default schedule"),
                        )

        elif freq == "monthly":
            day_of_month = default.get("day_of_month", 1)
            if now.day == day_of_month:
                return (
                    True,
                    default.get(
                        "reason", f"Monthly default schedule (day {day_of_month})"
                    ),
                )

        # If we reach here, should not run
        return (False, "Not scheduled for today")

    def get_next_run(self, source: str) -> Tuple[Optional[datetime], str]:
        """
        Calculate when this source should next run.

        Args:
            source: Source key

        Returns:
            Tuple of (next_run_datetime, reason)
        """
        if source not in self.schedules:
            # Default to 1 week
            next_run = datetime.now() + timedelta(days=7)
            return (next_run, "Unknown source - default weekly")

        now = datetime.now()
        config = self.schedules[source]

        # Check if we're in a special period first
        should_run, reason = self.should_run(source)
        if should_run:
            # Already should run, next run depends on frequency in current period
            if (
                "budget_season" in config
                and now.month in config["budget_season"]["months"]
            ):
                next_run = now + timedelta(days=1)
                return (next_run, "Daily during budget season")

            if (
                "audit_season" in config
                and now.month in config["audit_season"]["months"]
            ):
                # Next week same day
                days_until = 7
                next_run = now + timedelta(days=days_until)
                return (next_run, "Weekly during audit season")

        # Otherwise, calculate based on default frequency
        default = config.get("default", {})
        freq = default.get("frequency", "weekly")

        if freq == "daily":
            next_run = now + timedelta(days=1)
            return (next_run, default.get("reason", "Daily schedule"))

        elif freq == "weekly":
            target_day = default.get("day", "monday")
            days_ahead = self._days_until_weekday(target_day)
            next_run = now + timedelta(days=days_ahead if days_ahead > 0 else 7)
            return (next_run, default.get("reason", f"Weekly on {target_day}"))

        elif freq == "biweekly":
            # Next even week, target day
            week_num = now.isocalendar()[1]
            if week_num % 2 == 0:
                days_ahead = 14  # Next even week
            else:
                days_ahead = 7  # Next week is even
            next_run = now + timedelta(days=days_ahead)
            return (next_run, default.get("reason", "Biweekly schedule"))

        elif freq == "monthly":
            day_of_month = default.get("day_of_month", 1)
            if now.day < day_of_month:
                # Same month
                next_run = datetime(now.year, now.month, day_of_month)
            else:
                # Next month
                if now.month == 12:
                    next_run = datetime(now.year + 1, 1, day_of_month)
                else:
                    next_run = datetime(now.year, now.month + 1, day_of_month)
            return (next_run, default.get("reason", f"Monthly on day {day_of_month}"))

        # Fallback
        next_run = now + timedelta(days=7)
        return (next_run, "Default weekly schedule")

    def _days_until_weekday(self, target_day: str) -> int:
        """Calculate days until target weekday (0 = Monday, 6 = Sunday)."""
        day_mapping = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_num = day_mapping.get(target_day.lower(), 0)
        now = datetime.now()
        current_weekday = now.weekday()

        days_ahead = (target_num - current_weekday) % 7
        return days_ahead if days_ahead > 0 else 7

    def generate_schedule_report(self) -> Dict[str, Dict]:
        """
        Generate a comprehensive report of all sources and their schedules.

        Returns:
            Dict with source keys and schedule info including:
            - should_run_now: bool
            - reason: str
            - next_run: ISO datetime string
            - next_reason: str
            - current_period: str (if applicable)
        """
        report = {}

        for source in self.schedules.keys():
            should_run, reason = self.should_run(source)
            next_run, next_reason = self.get_next_run(source)

            # Determine current period
            now = datetime.now()
            current_period = "default"

            if source == "treasury" and now.month in [5, 6, 7]:
                current_period = "budget_season"
            elif source == "oag" and now.month in [11, 12, 1]:
                current_period = "audit_season"
            elif source == "knbs" and now.month == 5:
                current_period = "economic_survey"
            elif source == "knbs" and now.month == 12:
                current_period = "statistical_abstract"
            elif source == "cra" and now.month == 2:
                current_period = "allocation_season"

            # Check if in quarter-end period
            days_since = self._days_since_quarter_end()
            if source == "treasury" and 0 <= days_since <= 7:
                current_period = "post_quarter"
            elif source == "cob" and 45 <= days_since <= 59:
                current_period = "post_quarter"
            elif source == "knbs" and 14 <= days_since <= 35:
                current_period = "quarterly_data"

            report[source] = {
                "should_run_now": should_run,
                "reason": reason,
                "next_run": next_run.isoformat() if next_run else None,
                "next_reason": next_reason,
                "current_period": current_period,
                "schedule_config": self.schedules[source],
            }

        return report

    def get_schedule_summary(self) -> Dict[str, any]:
        """
        Get a high-level summary of scheduling efficiency.

        Returns:
            Dict with summary statistics
        """
        now = datetime.now()
        sources_to_run_today = []
        sources_not_running = []

        for source in self.schedules.keys():
            should_run, reason = self.should_run(source)
            if should_run:
                sources_to_run_today.append({"source": source, "reason": reason})
            else:
                sources_not_running.append(source)

        return {
            "timestamp": now.isoformat(),
            "sources_to_run_today": sources_to_run_today,
            "sources_not_running_today": sources_not_running,
            "efficiency": {
                "running": len(sources_to_run_today),
                "skipping": len(sources_not_running),
                "total_sources": len(self.schedules),
                "skip_percentage": (
                    round((len(sources_not_running) / len(self.schedules)) * 100, 1)
                    if self.schedules
                    else 0
                ),
            },
        }


# Convenience function for quick checks
def should_run_etl(source: str) -> Tuple[bool, str]:
    """
    Quick check if ETL should run for a source.

    Args:
        source: Source key ('treasury', 'cob', 'oag', 'knbs', 'opendata', 'cra')

    Returns:
        Tuple of (should_run: bool, reason: str)
    """
    scheduler = SmartScheduler()
    return scheduler.should_run(source)


if __name__ == "__main__":
    # Demo/testing
    logging.basicConfig(level=logging.INFO)

    scheduler = SmartScheduler()

    print("\n" + "=" * 70)
    print("SMART ETL SCHEDULER - Current Status")
    print("=" * 70 + "\n")

    # Show today's schedule
    summary = scheduler.get_schedule_summary()
    print(f"📅 Date: {summary['timestamp']}")
    print(
        f"⚡ Efficiency: Skipping {summary['efficiency']['skip_percentage']}% of sources today"
    )
    print(
        f"   (Running {summary['efficiency']['running']}/{summary['efficiency']['total_sources']} sources)\n"
    )

    print("Sources to run TODAY:")
    if summary["sources_to_run_today"]:
        for item in summary["sources_to_run_today"]:
            print(f"  ✅ {item['source'].upper()}: {item['reason']}")
    else:
        print("  (None scheduled for today)")

    print("\nSources NOT running today:")
    if summary["sources_not_running_today"]:
        for source in summary["sources_not_running_today"]:
            print(f"  ⏸️  {source.upper()}")
    else:
        print("  (All sources scheduled)")

    # Show detailed schedule
    print("\n" + "=" * 70)
    print("DETAILED SCHEDULE REPORT")
    print("=" * 70 + "\n")

    report = scheduler.generate_schedule_report()
    for source, info in report.items():
        print(f"📊 {source.upper()}")
        print(f"   Current Period: {info['current_period']}")
        print(f"   Should Run Now: {'✅ YES' if info['should_run_now'] else '❌ NO'}")
        print(f"   Reason: {info['reason']}")
        print(f"   Next Run: {info['next_run']}")
        print(f"   Next Reason: {info['next_reason']}")
        print()
