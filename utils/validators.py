"""
utils/validators.py
--------------------
Pure, reusable validation functions for common "semantic" data types that
pandas dtypes can't express: emails, phone numbers, URLs, and postal codes.
These are used by the issue detector to flag invalid values inside columns
that otherwise look like plain strings.
"""

from __future__ import annotations
import re
from typing import Optional

try:
    from email_validator import validate_email, EmailNotValidError
    _HAS_EMAIL_VALIDATOR = True
except ImportError:  # pragma: no cover
    _HAS_EMAIL_VALIDATOR = False

try:
    import phonenumbers
    _HAS_PHONENUMBERS = True
except ImportError:  # pragma: no cover
    _HAS_PHONENUMBERS = False


URL_REGEX = re.compile(
    r"^(https?:\/\/)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z]{2,})+([\/\w\-.~:?#@!$&'()*+,;=%]*)?$"
)
INDIA_PINCODE_REGEX = re.compile(r"^[1-9][0-9]{5}$")
US_ZIPCODE_REGEX = re.compile(r"^\d{5}(-\d{4})?$")
SPECIAL_CHAR_REGEX = re.compile(r"[^a-zA-Z0-9\s.,\-_@]")


def is_valid_email(value: str) -> bool:
    """Return True if `value` is a syntactically valid, deliverable-format email."""
    if not isinstance(value, str) or not value.strip():
        return False
    if _HAS_EMAIL_VALIDATOR:
        try:
            validate_email(value, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False
    # Fallback regex if the library isn't installed
    simple_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(simple_pattern, value.strip()))


def is_valid_phone(value: str, region: str = "IN") -> bool:
    """Return True if `value` parses as a valid phone number for the given region."""
    if not isinstance(value, (str, int)):
        return False
    value = str(value).strip()
    if not value:
        return False
    if _HAS_PHONENUMBERS:
        try:
            parsed = phonenumbers.parse(value, region)
            return phonenumbers.is_valid_number(parsed)
        except phonenumbers.NumberParseException:
            return False
    # Fallback: naive digit-count heuristic
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 15


def is_valid_url(value: str) -> bool:
    """Return True if `value` looks like a well-formed URL."""
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(URL_REGEX.match(value.strip()))


def is_valid_pincode(value: str, country: str = "IN") -> bool:
    """Return True if `value` matches a postal code pattern for the given country."""
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    if country == "IN":
        return bool(INDIA_PINCODE_REGEX.match(value))
    if country == "US":
        return bool(US_ZIPCODE_REGEX.match(value))
    # Generic fallback: 4-10 alphanumeric characters
    return bool(re.match(r"^[A-Za-z0-9\- ]{4,10}$", value))


def has_special_characters(value: str) -> bool:
    """Return True if `value` contains characters outside common safe ranges."""
    if not isinstance(value, str):
        return False
    return bool(SPECIAL_CHAR_REGEX.search(value))


def has_inconsistent_case(series_sample) -> bool:
    """
    Heuristic: return True if a text column mixes multiple casing styles
    (e.g. 'New York', 'new york', 'NEW YORK' all present as distinct values).
    """
    values = [str(v).strip() for v in series_sample if isinstance(v, str) and v.strip()]
    if len(values) < 2:
        return False
    lowered = {v.lower() for v in values}
    original = set(values)
    return len(lowered) < len(original)


def guess_boolean_like(series_sample) -> Optional[set]:
    """
    Inspect a small sample of a column and return the set of distinct
    non-null values if they look like a boolean encoded as text/numbers
    (e.g. {'Yes', 'No'}, {'Y', 'N'}, {0, 1}, {'True', 'False'}).
    Returns None if the column doesn't look boolean-like.
    """
    known_boolean_sets = [
        {"yes", "no"}, {"y", "n"}, {"true", "false"}, {"t", "f"},
        {"0", "1"}, {"male", "female"},
    ]
    distinct = {str(v).strip().lower() for v in series_sample if v is not None and str(v).strip()}
    if not distinct or len(distinct) > 4:
        return None
    for known in known_boolean_sets:
        if distinct <= known:
            return distinct
    return None
