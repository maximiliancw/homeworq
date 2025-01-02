from typing import List, Optional, Union

from .schemas import JobSchedule, TimeUnit


def _parse_cron_field(
    field: str, options: List[str], allow_any: bool = True
) -> Optional[List[int]]:
    """Parse a single cron field into a list of integers."""
    if field == "*":
        return None if allow_any else [i for i in range(len(options))]

    values = []
    for part in field.split(","):
        if "-" in part:
            start, end = map(
                lambda x: options.index(x) if x in options else int(x),
                part.split("-"),
            )
            values.extend(range(start, end + 1))
        elif "/" in part:
            step_range, step = part.split("/")
            start = 0 if step_range == "*" else int(step_range)
            values.extend(range(start, len(options), int(step)))
        else:
            values.append(options.index(part) if part in options else int(part))
    return sorted(set(values))


def _format_time_list(
    values: List[int],
    options: Optional[List[str]] = None,
) -> str:
    """Format a list of integers into a human-readable string."""
    if not values:
        return ""

    if options:
        values = [options[v] for v in values]

    if len(values) == 1:
        return str(values[0])

    if len(values) == 2:
        return f"{values[0]} and {values[1]}"

    return f"{', '.join(map(str, values[:-1]))}, and {values[-1]}"


def format_schedule(schedule: Union[JobSchedule, str]) -> str:
    """
    Convert a schedule into a human-readable format.

    Args:
        schedule: Either a JobSchedule object or a cron-syntax string

    Returns:
        str: Human-readable description of the schedule

    Examples:
        >>> format_schedule("0 0 * * *")
        "Every day at midnight"
        >>> format_schedule(JobSchedule(interval=2, unit=TimeUnit.HOURS))
        "Every 2 hours"
        >>> format_schedule(JobSchedule(interval=1, unit=TimeUnit.DAYS, at="09:30"))
        "Every day at 09:30"
    """
    if isinstance(schedule, str):
        # Parse cron expression (minute hour day_of_month month day_of_week)
        try:
            minute, hour, dom, month, dow = schedule.split()

            months = [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ]
            days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

            # Parse each field
            minutes = _parse_cron_field(minute, [str(i) for i in range(60)])
            hours = _parse_cron_field(hour, [str(i) for i in range(24)])
            days_of_month = _parse_cron_field(dom, [str(i) for i in range(1, 32)])
            months_list = _parse_cron_field(
                month, [str(i) for i in range(1, 13)] + months
            )
            days_of_week = _parse_cron_field(dow, [str(i) for i in range(7)] + days)

            # Build the description
            parts = []

            # Time part
            if minutes == [0] and hours == [0]:
                time_str = "midnight"
            elif minutes == [0] and hours == [12]:
                time_str = "noon"
            else:
                if hours and minutes:
                    hours_fmt = _format_time_list(hours)
                    mins_fmt = _format_time_list(minutes)
                    time_str = (
                        f"{hours_fmt}:{mins_fmt:02d}"
                        if len(minutes) == 1
                        else f"{hours_fmt}:{mins_fmt}"
                    )
                else:
                    time_str = "every hour" if not hours else "every minute"

            parts.append(f"at {time_str}" if "every" not in time_str else time_str)

            # Days part
            if days_of_week:
                days_str = _format_time_list(days_of_week, days)
                parts.append(f"on {days_str}")
            elif days_of_month:
                days_str = _format_time_list(days_of_month)
                parts.append(f"on day {days_str}")

            # Months part
            if months_list:
                months_str = _format_time_list(months_list, months)
                parts.append(f"in {months_str}")

            return " ".join(parts).capitalize()

        except Exception as e:
            raise ValueError(f"Invalid cron expression: {str(e)}")

    # Handle JobSchedule object
    interval = schedule.interval
    unit = schedule.unit
    at_time = schedule.at

    # Handle singular/plural units
    unit_str = unit.value
    if interval == 1:
        if unit == TimeUnit.HOURS:
            unit_str = "hour"
        elif unit == TimeUnit.DAYS:
            return f"Every day{f' at {at_time}' if at_time else ''}"
        elif unit == TimeUnit.WEEKS:
            unit_str = "week"
        elif unit == TimeUnit.MONTHS:
            unit_str = "month"
        elif unit == TimeUnit.YEARS:
            unit_str = "year"
        else:
            unit_str = unit_str[:-1]  # Remove 's' for other units

    base = f"Every {interval} {unit_str}"

    if at_time:
        return f"{base} at {at_time}"

    return base
