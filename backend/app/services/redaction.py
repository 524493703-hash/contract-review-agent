from __future__ import annotations

import re


PATTERNS = (
    ("身份证号", re.compile(r"(?<!\d)(\d{6})\d{8}([0-9Xx]{4})(?!\d)"), r"\1********\2"),
    ("手机号", re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)"), r"\1****\2"),
    ("电子邮箱", re.compile(r"([A-Za-z0-9._%+-]{1,3})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"), r"\1***\2"),
    ("银行卡号", re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)"), r"\1********\2"),
)


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    redacted = text
    counts: dict[str, int] = {}
    for label, pattern, replacement in PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        counts[label] = count
    return redacted, counts
