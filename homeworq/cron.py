from datetime import datetime, timezone
from typing import List, Optional, Tuple


class CronParser:
    """Parser for cron expressions that calculates the next run time."""

    FIELDS = ["minute", "hour", "day", "month", "day_of_week"]
    RANGES = {
        "minute": (0, 59),
        "hour": (0, 23),
        "day": (1, 31),
        "month": (1, 12),
        "day_of_week": (0, 6),  # 0 = Sunday
    }

    def __init__(self, cron_expr: str):
        self.original = cron_expr
        self.fields = self._parse_expr(cron_expr)

    def _parse_field(self, field: str, field_name: str) -> List[int]:
        """Parse a single cron field into a list of valid values."""
        field_range = self.RANGES[field_name]
        result = set()

        # Handle multiple comma-separated values
        for part in field.split(","):
            if part == "*":
                result.update(range(field_range[0], field_range[1] + 1))
                continue

            # Handle step values
            if "/" in part:
                range_part, step = part.split("/")
                step = int(step)

                if range_part == "*":
                    start, end = field_range
                else:
                    if "-" in range_part:
                        start, end = map(int, range_part.split("-"))
                    else:
                        start = int(range_part)
                        end = field_range[1]

                result.update(range(start, end + 1, step))
                continue

            # Handle ranges
            if "-" in part:
                start, end = map(int, part.split("-"))
                result.update(range(start, end + 1))
                continue

            # Handle single values
            result.add(int(part))

        # Validate values are within allowed range
        for value in result:
            if not field_range[0] <= value <= field_range[1]:
                raise ValueError(
                    f"Value {value} out of range for {field_name} "
                    f"({field_range[0]}-{field_range[1]})"
                )

        return sorted(list(result))

    def _parse_expr(self, expr: str) -> dict:
        """Parse full cron expression into structured format."""
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "Invalid cron expression. Must have 5 fields: "
                "minute hour day month day_of_week"
            )

        return {
            field: self._parse_field(value, field)
            for field, value in zip(self.FIELDS, parts)
        }

    def _get_next_value(
        self, current: int, allowed: List[int], rollover: bool = False
    ) -> Tuple[int, bool]:
        """Get next allowed value in sequence."""
        for value in allowed:
            if value > current or rollover:
                return value, False
        if allowed:  # If we didn't find a larger value, roll over to first
            return allowed[0], True
        raise ValueError("No valid values found")

    def get_next_run(self, after: Optional[datetime] = None) -> datetime:
        """Calculate the next run time after the given datetime."""
        if after is None:
            after = datetime.now(timezone.utc)

        current = after.replace(second=0, microsecond=0)

        while True:
            minute, minute_rollover = self._get_next_value(
                current.minute, self.fields["minute"]
            )

            if minute_rollover or minute > current.minute:
                current = current.replace(
                    minute=minute,
                    hour=current.hour + (1 if minute_rollover else 0),
                )
                continue

            hour, hour_rollover = self._get_next_value(
                current.hour, self.fields["hour"], minute_rollover
            )

            if hour_rollover or hour > current.hour:
                current = current.replace(
                    minute=self.fields["minute"][0],
                    hour=hour,
                )
                if hour_rollover:
                    current = current.replace(day=current.day + 1)
                continue

            # Check if current day of month and day of week are valid
            day_valid = current.day in self.fields["day"]
            dow_valid = current.weekday() in self.fields["day_of_week"]

            if not (day_valid and dow_valid):
                current = current.replace(
                    minute=self.fields["minute"][0],
                    hour=self.fields["hour"][0],
                    day=current.day + 1,
                )
                continue

            month_valid = current.month in self.fields["month"]
            if not month_valid:
                if current.month == 12:
                    current = current.replace(
                        year=current.year + 1,
                        month=1,
                        day=1,
                        hour=self.fields["hour"][0],
                        minute=self.fields["minute"][0],
                    )
                else:
                    current = current.replace(
                        month=current.month + 1,
                        day=1,
                        hour=self.fields["hour"][0],
                        minute=self.fields["minute"][0],
                    )
                continue

            # If we get here, we've found a valid time
            return current
