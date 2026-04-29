import re

from review_bot.domain.models import ReviewCommand

_PATTERN = re.compile(r"^\s*/review(?:\s+(\S+))?(?:\s+(.*))?\s*$")


def parse_review_command(note: str) -> ReviewCommand | None:
    m = _PATTERN.match(note or "")
    if not m:
        return None
    template = m.group(1) or "general"
    rest = m.group(2) or ""
    extra: dict[str, str] = {}
    for token in rest.split():
        if token.startswith("--") and "=" in token:
            k, v = token[2:].split("=", 1)
            extra[k] = v
    return ReviewCommand(template=template, extra_args=extra)
