import re


def cron_to_human_readable(cron: str) -> str:
    """
    Convert a cron-like syntax to a human-readable format.

    Args:
        cron (str): The cron-like syntax.

    Returns:
        str: The human-readable format.
    """
    cron_parts = cron.split()
    if len(cron_parts) != 5:
        return "Invalid cron syntax"

    minute, hour, day_of_month, month, day_of_week = cron_parts

    def parse_part(part, name):
        if part == "*":
            return f"every {name}"
        elif re.match(r"^\d+$", part):
            return f"at {part} {name}"
        elif re.match(r"^\*/\d+$", part):
            return f"every {part[2:]} {name}s"
        else:
            return f"on {part}"

    minute_str = parse_part(minute, "minute")
    hour_str = parse_part(hour, "hour")
    day_of_month_str = parse_part(day_of_month, "day")
    month_str = parse_part(month, "month")
    day_of_week_str = parse_part(day_of_week, "day of the week")

    return (
        f"{minute_str}, {hour_str}, {day_of_month_str}, "
        f"{month_str}, {day_of_week_str}"
    )
