"""PII sanitiser — NFR-16 (CRITICAL).

Removes/masks personal data from resume text BEFORE sending to external LLM:
  - Email addresses
  - Phone numbers (Russian & international)
  - URLs / social media links
  - Full names (Russian ФИО heuristics)
  - Dates of birth
  - Physical addresses (partial heuristics)
  - Telegram/WhatsApp/Skype handles
  - Passport/SNILS/INN numbers

The sanitiser logs HOW MANY entities were removed, but NEVER the PII itself.
Raw text with PII is NOT persisted (NFR-14).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class SanitisationResult:
    """Result of PII sanitisation."""
    sanitised_text: str
    entities_removed: int = 0
    categories: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Regex patterns for PII detection
# ---------------------------------------------------------------------------

# Email: standard pattern
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone numbers: Russian (+7, 8) and international formats
_PHONE_RE = re.compile(
    # +7/8 (XXX) XXX-XX-XX
    r"(?:(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})"
    # international
    r"|(?:\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{2,4})"
    # X (XXX) XXX-XX-XX
    r"|(?:\b\d[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b)",
    re.VERBOSE,
)

# URLs: http(s) and www
_URL_RE = re.compile(
    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+",
    re.IGNORECASE,
)

# Social media / messenger handles
_SOCIAL_RE = re.compile(
    r"(?:@[A-Za-z0-9_]{2,30})"  # @username
    r"|(?:(?:t\.me|telegram\.me|vk\.com|facebook\.com|linkedin\.com|github\.com|instagram\.com|twitter\.com|wa\.me)/[^\s<>\"']+)"
    r"|(?:(?:skype|telegram|whatsapp|viber)[\s:]+[A-Za-z0-9_.@\-]+)",
    re.IGNORECASE,
)

# Russian full names (ФИО): Capitalized Cyrillic words pattern
# Pattern: 2-3 consecutive capitalised Cyrillic words. Handles BOTH common
# orders — "Фамилия Имя Отчество" AND "Имя Отчество Фамилия" — by capturing up
# to three words generically; the patronymic is detected in any position by
# _is_likely_fio (so a trailing surname is removed too — NFR-16).
_FIO_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]{1,20})\s+([А-ЯЁ][а-яё]{1,20})(?:\s+([А-ЯЁ][а-яё]{1,20}))?\b"
)

# Patronymic endings used to recognise a Russian middle name (Отчество).
_PATRONYMIC_SUFFIXES = ("вич", "вна", "ич", "на")

# Date of birth patterns
_DOB_RE = re.compile(
    r"\b(?:дата\s+рождения|д\.?\s*р\.?|родил(?:ся|ась)|born)[\s:]*"
    r"(\d{1,2}[\s./\-]\d{1,2}[\s./\-]\d{2,4})",
    re.IGNORECASE,
)

# Standalone dates that might be DOB (DD.MM.YYYY near age/birth context)
_DATE_STANDALONE_RE = re.compile(
    r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b"
)

# Passport, SNILS, INN
_PASSPORT_RE = re.compile(
    r"\b(?:паспорт|passport)[\s:]*\d{2}\s*\d{2}\s*\d{6}\b",
    re.IGNORECASE,
)
_SNILS_RE = re.compile(
    r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}\b"
)
_INN_RE = re.compile(
    r"\b(?:ИНН|INN)[\s:]*\d{10,12}\b",
    re.IGNORECASE,
)

# Physical address heuristics (Russian)
_ADDRESS_RE = re.compile(
    r"(?:г\.\s*[А-ЯЁа-яё]+|ул\.\s*[А-ЯЁа-яё\s]+|пр\.\s*[А-ЯЁа-яё\s]+|"
    r"д\.\s*\d+|кв\.\s*\d+|корп\.\s*\d+|стр\.\s*\d+|"
    r"пос\.\s*[А-ЯЁа-яё]+|обл\.\s*[А-ЯЁа-яё]+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# FIO filtering: skip common non-name words
# ---------------------------------------------------------------------------

# Common words that look like FIO but aren't (job titles, section headers, etc.)
_FIO_SKIP_WORDS = frozenset({
    # Section headers / common resume terms
    "Опыт", "Работы", "Образование", "Навыки", "Проекты", "Языки",
    "Контакты", "Резюме", "Компания", "Должность", "Период",
    "Описание", "Достижения", "Сертификаты", "Курсы",
    "Ожидаемая", "Зарплата", "Город", "Возраст",
    # Common tech words that start with capital
    "Junior", "Middle", "Senior", "Frontend", "Backend", "Fullstack",
    "React", "Angular", "Python", "JavaScript", "TypeScript",
    "Разработчик", "Программист", "Инженер", "Менеджер",
    "Высшее", "Среднее",
})


def _is_likely_fio(match: re.Match) -> bool:
    """Heuristic: is a regex match likely a real FIO (not a heading)?

    Handles both Russian name orders:
      • "Фамилия Имя Отчество"  (patronymic last)
      • "Имя Отчество Фамилия"  (patronymic in the middle)
    When a patronymic is present in ANY captured word, the entire span —
    including a trailing/leading surname — is treated as PII (NFR-16).
    """
    first = match.group(1)
    second = match.group(2)
    third = match.group(3)
    # Skip if any word is a known non-name (section header / tech term)
    if first in _FIO_SKIP_WORDS or second in _FIO_SKIP_WORDS:
        return False
    if third and third in _FIO_SKIP_WORDS:
        return False
    # If ANY word looks like a patronymic, this is almost certainly a real
    # ФИО — remove the whole match (surname included, regardless of order).
    words = [w for w in (first, second, third) if w]
    if any(w.endswith(_PATRONYMIC_SUFFIXES) for w in words):
        return True
    # No patronymic detected → only treat a plain two-word head as a name if
    # the third group is absent (avoid greedily eating a trailing real word)
    # and both words are ≥ 3 chars (skip abbreviations / short headings).
    if third is not None:
        return False
    return len(first) >= 3 and len(second) >= 3


# ---------------------------------------------------------------------------
# Main sanitiser
# ---------------------------------------------------------------------------

_PLACEHOLDER = "[УДАЛЕНО]"


def sanitise_pii(text: str) -> SanitisationResult:
    """Remove PII from resume text.

    Returns SanitisationResult with sanitised text and counts.
    Logs the NUMBER of entities removed per category, but NEVER the PII values.
    """
    counts: dict[str, int] = {}
    result = text

    def _replace(pattern: re.Pattern, category: str, text_: str) -> str:
        matches = pattern.findall(text_)
        if matches:
            counts[category] = counts.get(category, 0) + len(matches)
        return pattern.sub(_PLACEHOLDER, text_)

    def _replace_fio(text_: str) -> str:
        """Replace FIO with heuristic filtering."""
        removed = 0

        def _repl(m: re.Match) -> str:
            nonlocal removed
            if _is_likely_fio(m):
                removed += 1
                return _PLACEHOLDER
            return m.group(0)
        result_ = _FIO_RE.sub(_repl, text_)
        if removed:
            counts["fio"] = counts.get("fio", 0) + removed
        return result_

    # Order matters: emails BEFORE socials (socials' @username matches inside emails)
    result = _replace(_EMAIL_RE, "email", result)
    result = _replace(_URL_RE, "url", result)
    result = _replace(_SOCIAL_RE, "social", result)
    result = _replace(_PHONE_RE, "phone", result)
    result = _replace(_DOB_RE, "dob", result)
    result = _replace(_PASSPORT_RE, "passport", result)
    result = _replace(_INN_RE, "inn", result)
    result = _replace(_SNILS_RE, "snils", result)
    result = _replace(_ADDRESS_RE, "address", result)
    result = _replace_fio(result)

    total_removed = sum(counts.values())

    # Log counts only — NEVER log PII values (NFR-16, NFR-17)
    if total_removed > 0:
        logger.info(
            "pii_sanitised",
            entities_removed=total_removed,
            categories=counts,
        )
    else:
        logger.debug("pii_sanitisation_clean", entities_removed=0)

    return SanitisationResult(
        sanitised_text=result,
        entities_removed=total_removed,
        categories=counts,
    )
