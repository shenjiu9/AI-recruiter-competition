from datetime import UTC, datetime, timedelta, timezone


class WorkCalendar:
    """Shanghai business dates; deployment supplies holiday and make-up workday overrides."""

    def __init__(self, holidays=(), workdays=()):
        self.holidays, self.workdays = set(holidays), set(workdays)

    def deadline(self, timestamp):
        value = datetime.fromisoformat(timestamp).astimezone(timezone(timedelta(hours=8)))
        remaining = 3
        while remaining:
            value += timedelta(days=1)
            day = value.date()
            if day in self.workdays or (day.weekday() < 5 and day not in self.holidays):
                remaining -= 1
        return value.astimezone(UTC)
