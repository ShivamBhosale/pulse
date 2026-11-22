"""Tags and notes you enter yourself: CRUD, day journal, and the queries behind tag effects.

These tables are never touched by sync. Tags are archived, never deleted, so history stays.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from pulse.models import DayNote, DayTag, Tag

NOTE_MAX = 2000
LABEL_MAX = 40
KINDS = ("evening", "day")
SICK_KEY = "sick"


class JournalError(ValueError):
    """Invalid journal input (maps to HTTP 422)."""


class TagExists(JournalError):
    """A tag with this key already exists (maps to HTTP 409)."""


def slugify(label: str) -> str:
    s = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:48]


@dataclass(frozen=True)
class TagInfo:
    key: str
    label: str
    kind: str
    archived: bool
    uses: int
    last_used: date | None


def list_tags(session: Session, include_archived: bool = True) -> list[TagInfo]:
    usage = {
        k: (n, last)
        for k, n, last in session.execute(
            select(DayTag.tag_key, func.count(), func.max(DayTag.civil_date)).group_by(
                DayTag.tag_key
            )
        )
    }
    q = select(Tag).order_by(Tag.archived, Tag.sort, Tag.label)
    if not include_archived:
        q = q.where(Tag.archived.is_(False))
    return [
        TagInfo(t.key, t.label, t.kind, t.archived, *usage.get(t.key, (0, None)))
        for t in session.scalars(q)
    ]


def _clean_label(label: str) -> str:
    label = " ".join(label.split())
    if not label or len(label) > LABEL_MAX:
        raise JournalError(f"label must be 1-{LABEL_MAX} characters")
    return label


def create_tag(session: Session, label: str, kind: str, now: datetime) -> Tag:
    label = _clean_label(label)
    if kind not in KINDS:
        raise JournalError(f"kind must be one of {', '.join(KINDS)}")
    key = slugify(label)
    if not key:
        raise JournalError("label needs at least one letter or digit")
    if session.get(Tag, key) is not None:
        raise TagExists(f"a tag called {label!r} already exists")
    sort = (session.execute(select(func.max(Tag.sort))).scalar() or 0) + 1
    tag = Tag(key=key, label=label, kind=kind, archived=False, sort=sort, created_at=now)
    session.add(tag)
    return tag


def update_tag(
    session: Session,
    key: str,
    *,
    label: str | None = None,
    kind: str | None = None,
    archived: bool | None = None,
) -> Tag | None:
    tag = session.get(Tag, key)
    if tag is None:
        return None
    if label is not None:
        tag.label = _clean_label(label)
    if kind is not None:
        if kind not in KINDS:
            raise JournalError(f"kind must be one of {', '.join(KINDS)}")
        tag.kind = kind
    if archived is not None:
        tag.archived = archived
    return tag


@dataclass(frozen=True)
class DayJournal:
    date: date
    tags: list[str]
    note: str


def get_journal(session: Session, d: date) -> DayJournal:
    tags = [
        k
        for (k,) in session.execute(
            select(DayTag.tag_key)
            .join(Tag, Tag.key == DayTag.tag_key)
            .where(DayTag.civil_date == d)
            .order_by(Tag.sort)
        )
    ]
    note = session.get(DayNote, d)
    return DayJournal(d, tags, note.text if note else "")


def put_journal(session: Session, d: date, tags: list[str], note: str, now: datetime) -> DayJournal:
    """Replace the day's tags and note. Tags already on the day may stay even if archived
    since; adding an archived or unknown tag is refused."""
    if len(note) > NOTE_MAX:
        raise JournalError(f"note is limited to {NOTE_MAX} characters")
    wanted = list(dict.fromkeys(tags))  # dedupe, keep order
    existing = set(get_journal(session, d).tags)
    known = {t.key: t for t in session.scalars(select(Tag).where(Tag.key.in_(wanted)))}
    unknown = [k for k in wanted if k not in known]
    if unknown:
        raise JournalError(f"unknown tags: {', '.join(unknown)}")
    newly_archived = [k for k in wanted if known[k].archived and k not in existing]
    if newly_archived:
        raise JournalError(f"archived tags can't be added: {', '.join(newly_archived)}")
    session.execute(delete(DayTag).where(DayTag.civil_date == d))
    session.add_all(DayTag(civil_date=d, tag_key=k, created_at=now) for k in wanted)
    text = note.strip()
    row = session.get(DayNote, d)
    if text:
        if row is None:
            session.add(DayNote(civil_date=d, text=text, updated_at=now))
        elif row.text != text:
            row.text, row.updated_at = text, now
    elif row is not None:
        session.delete(row)
    session.flush()
    return get_journal(session, d)


def journal_range(session: Session, start: date, end_inclusive: date) -> list[DayJournal]:
    tags: dict[date, list[str]] = defaultdict(list)
    for d, k in session.execute(
        select(DayTag.civil_date, DayTag.tag_key)
        .join(Tag, Tag.key == DayTag.tag_key)
        .where(DayTag.civil_date >= start, DayTag.civil_date <= end_inclusive)
        .order_by(DayTag.civil_date, Tag.sort)
    ):
        tags[d].append(k)
    notes = {
        n.civil_date: n.text
        for n in session.scalars(
            select(DayNote).where(DayNote.civil_date >= start, DayNote.civil_date <= end_inclusive)
        )
    }
    return [
        DayJournal(d, tags.get(d, []), notes.get(d, "")) for d in sorted(set(tags) | set(notes))
    ]


def tag_days(session: Session, key: str) -> set[date]:
    return set(session.scalars(select(DayTag.civil_date).where(DayTag.tag_key == key)))


def utcnow() -> datetime:
    return datetime.now(UTC)
