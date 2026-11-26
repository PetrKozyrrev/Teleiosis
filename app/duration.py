from sqlalchemy import Integer, Numeric, case, cast, func

from app.models import Content

CHARACTERS_PER_MINUTE = 1000
SECONDS_PER_MINUTE = 60
# The whitespace that Python str.split() treats as separators, independent of DB collation.
NOTE_WHITESPACE = (
    "\t\n\v\f\r\x1c\x1d\x1e\x1f\x85\xa0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)


def reading_minutes(kind: str, url: str | None, note: str | None, characters: int | None) -> int | None:
    if kind == "video":
        return None
    if url is None and kind != "pdf" and note:
        characters = len(" ".join(note.split()))
    return (characters + CHARACTERS_PER_MINUTE - 1) // CHARACTERS_PER_MINUTE if characters else None


def estimated_minutes(content: Content) -> int | None:
    seconds = content.video_duration_seconds
    if seconds and seconds > 0:
        return (seconds + SECONDS_PER_MINUTE - 1) // SECONDS_PER_MINUTE
    return reading_minutes(content.content_type, content.url, content.note, content.text_character_count)


def estimated_minutes_sql(*, normalize_notes: bool = True):
    trimmed = func.btrim(Content.note, " " + NOTE_WHITESPACE)
    # Ordinary single spaces already match Python's normalization.
    # For a presence check, trimming alone distinguishes empty and nonempty notes.
    if normalize_notes:
        trimmed = func.regexp_replace(trimmed, f"[ {NOTE_WHITESPACE}]{{2,}}|[{NOTE_WHITESPACE}]", " ", "g")
    note_characters = func.char_length(trimmed)
    characters = case(
        (Content.url.is_(None) & (Content.content_type != "pdf") & (Content.note != ""), note_characters),
        else_=Content.text_character_count,
    )
    return case(
        (Content.video_duration_seconds > 0, func.ceil(cast(Content.video_duration_seconds, Numeric) / SECONDS_PER_MINUTE)),
        ((Content.content_type != "video") & (characters > 0), func.ceil(cast(characters, Numeric) / CHARACTERS_PER_MINUTE)),
        else_=None,
    ).cast(Integer)
