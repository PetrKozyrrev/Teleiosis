"""Validation and account-local planning for Teleiosis export v1."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timezone
from hashlib import sha256
import json
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, ValidationError, field_validator
from sqlalchemy import Text, func, select, tuple_
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from app.export import EXPORT_VERSION
from app.models import Category, Content, ContentGroup, LibraryGroup, LibraryImport
from app.routers.organization import GROUP_LIMIT
from app.schemas import MAX_BIGINT, CategoryName, ContentStatus
from app.urls import clean_url, detect_source, normalize_url

FILE_LIMIT = 2 * 1024 * 1024
MATERIAL_LIMIT = 500
ASSIGNMENT_LIMIT = 20
ImportId = Annotated[int, Field(strict=True, gt=0, le=MAX_BIGINT)]
GroupKind = Literal["tag", "collection"]


class InvalidExport(ValueError):
    def __init__(self, code: str, location: tuple = ()):
        self.code = code
        self.location = location


class ExportRow(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def valid_text(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("NUL is unsupported")
            value.encode("utf-8")  # Reject isolated surrogates from JSON escapes.
        return value


class ExportName(ExportRow):
    id: ImportId
    name: CategoryName


class ExportMaterial(ExportRow):
    id: ImportId
    category_id: ImportId | None = None
    title: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    note: Annotated[str, StringConstraints(max_length=10_000)] | None = None
    description: Annotated[str, StringConstraints(max_length=10_000)] | None = None
    url: str | None = None
    image_url: str | None = None
    status: ContentStatus = "unseen"
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    studied_at: AwareDatetime | None = None
    last_opened_at: AwareDatetime | None = None
    open_count: Annotated[int, Field(strict=True, ge=0, le=2_147_483_647)] = 0

    @field_validator("url", "image_url")
    @classmethod
    def validate_url(cls, value):
        if value is None:
            return None
        if not value.lower().startswith(("http://", "https://")) or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("Invalid URL")
        return clean_url(value)

    @field_validator("created_at", "updated_at", "studied_at", "last_opened_at", mode="before")
    @classmethod
    def validate_date_text(cls, value):
        if value is not None and (not isinstance(value, str) or "T" not in value):
            raise ValueError("Expected ISO 8601 date and time")
        return value

    @field_validator("created_at", "updated_at", "studied_at", "last_opened_at")
    @classmethod
    def validate_date_range(cls, value):
        try:
            return value.astimezone(timezone.utc) if value is not None else None
        except OverflowError:
            raise ValueError("Date outside the supported range") from None


class ExportMembership(ExportRow):
    content_id: ImportId
    group_id: ImportId


class ExportDocument(BaseModel):
    version: Annotated[int, Field(strict=True)]
    categories: list[ExportName] = Field(max_length=200)
    contents: list[ExportMaterial] = Field(max_length=MATERIAL_LIMIT)
    tags: list[ExportName] = Field(default_factory=list, max_length=GROUP_LIMIT)
    collections: list[ExportName] = Field(default_factory=list, max_length=GROUP_LIMIT)
    organization: list[ExportMembership] = Field(
        default_factory=list, max_length=MATERIAL_LIMIT * ASSIGNMENT_LIMIT * 2,
    )


@dataclass
class ValidatedExport:
    digest: str
    document: ExportDocument
    urls: dict[int, str]
    memberships: dict[int, set[int]]

    @property
    def groups(self) -> list[tuple[GroupKind, ExportName]]:
        return [("tag", row) for row in self.document.tags] + [
            ("collection", row) for row in self.document.collections
        ]


def unique_members(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Repeated JSON key")
    return result


def reject_constant(_value):
    raise ValueError("Invalid JSON constant")


def validate_export(raw: bytes) -> ValidatedExport:
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_members, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise InvalidExport("invalid_json") from None
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != EXPORT_VERSION:
        raise InvalidExport("unsupported_export_version", ("version",))
    try:
        document = ExportDocument.model_validate(value)
    except ValidationError as error:
        issue = error.errors(include_input=False, include_context=False, include_url=False)[0]
        raise InvalidExport("invalid_export_field", issue["loc"]) from None

    def indexed(rows, field):
        result = {}
        for index, row in enumerate(rows):
            if row.id in result:
                raise InvalidExport("repeated_id", (field, index, "id"))
            result[row.id] = row
        return result

    categories = indexed(document.categories, "categories")
    materials = indexed(document.contents, "contents")
    tags = indexed(document.tags, "tags")
    collections = indexed(document.collections, "collections")
    if tags.keys() & collections.keys():
        raise InvalidExport("repeated_id", ("collections",))
    urls = {}
    for index, material in enumerate(document.contents):
        if material.category_id is not None and material.category_id not in categories:
            raise InvalidExport("unknown_reference", ("contents", index, "category_id"))
        if material.url:
            urls[material.id] = normalize_url(material.url)
        elif not material.note or not material.note.strip():
            raise InvalidExport("missing_material_content", ("contents", index))
    memberships = defaultdict(set)
    counts = Counter()
    for index, item in enumerate(document.organization):
        if item.content_id not in materials or (item.group_id not in tags and item.group_id not in collections):
            raise InvalidExport("unknown_reference", ("organization", index))
        selected = memberships[item.content_id]
        if item.group_id in selected:
            raise InvalidExport("repeated_membership", ("organization", index))
        selected.add(item.group_id)
        key = (item.content_id, item.group_id in tags)
        counts[key] += 1
        if counts[key] > ASSIGNMENT_LIMIT:
            raise InvalidExport("assignment_limit", ("organization", index))
    return ValidatedExport(sha256(raw).hexdigest(), document, urls, memberships)


class ImportSummary(BaseModel):
    materials: int = 0
    duplicates: int = 0
    categories: int = 0
    tags: int = 0
    collections: int = 0
    memberships: int = 0
    replayed: bool = False


def lower_names(db: Session, names: set[str]) -> dict[str, str]:
    if not names:
        return {}
    # Match the PostgreSQL lower(name) indexes, including the database collation.
    name = func.unnest(array(sorted(names), type_=Text)).column_valued("name")
    return {original: key for original, key in db.execute(select(name, func.lower(name)))}


def new_materials(db: Session, owner: int, data: ValidatedExport) -> list[ExportMaterial]:
    existing_urls = set(db.scalars(select(Content.url_normalized).where(
        Content.user_id == owner, Content.url_normalized.in_(set(data.urls.values())),
    )))
    notes = {(row.title, row.note) for row in data.document.contents if not row.url}
    existing_notes = {(title, note) for title, note in db.execute(select(Content.title, Content.note).where(
        Content.user_id == owner, Content.url.is_(None), tuple_(Content.title, Content.note).in_(notes),
    ))} if notes else set()

    selected = []
    for row in data.document.contents:
        if row.url:
            key = data.urls[row.id]
            if key in existing_urls:
                continue
            existing_urls.add(key)
        else:
            key = (row.title, row.note)
            if key in existing_notes:
                continue
            existing_notes.add(key)
        selected.append(row)
    return selected


class GroupQuotaError(ValueError):
    pass


def import_library(db: Session, owner: int, data: ValidatedExport, *, apply: bool) -> ImportSummary:
    receipt = db.get(LibraryImport, (owner, data.digest))
    if receipt is not None:
        return ImportSummary(**receipt.summary, replayed=True)

    doc = data.document
    groups = data.groups
    keys = lower_names(db, {row.name for row in doc.categories} | {row.name for _, row in groups})
    category_keys = {keys[row.name] for row in doc.categories}
    categories = {key: row for key, row in db.execute(
        select(func.lower(Category.name), Category).where(
            Category.user_id == owner, func.lower(Category.name).in_(category_keys),
        )
    )}
    library_groups = {(row.kind, key): row for key, row in db.execute(
        select(func.lower(LibraryGroup.name), LibraryGroup).where(LibraryGroup.user_id == owner)
    )}
    new_categories = {}
    for row in doc.categories:
        key = keys[row.name]
        if key not in categories:
            category = Category(user_id=owner, name=row.name)
            new_categories[key] = category
            categories[key] = category
    new_groups = {}
    for kind, row in groups:
        key = (kind, keys[row.name])
        if key not in library_groups:
            group = LibraryGroup(user_id=owner, kind=kind, name=row.name)
            new_groups[key] = group
            library_groups[key] = group
    if any(count > GROUP_LIMIT for count in Counter(kind for kind, _ in library_groups).values()):
        raise GroupQuotaError

    category_map = {row.id: categories[keys[row.name]] for row in doc.categories}
    group_map = {row.id: library_groups[kind, keys[row.name]] for kind, row in groups}
    selected = new_materials(db, owner, data)
    links = {row.id: {group_map[key] for key in data.memberships.get(row.id, ())} for row in selected}
    tags = sum(kind == "tag" for kind, _ in new_groups)
    result = ImportSummary(
        materials=len(selected), duplicates=len(doc.contents) - len(selected), categories=len(new_categories),
        tags=tags, collections=len(new_groups) - tags, memberships=sum(map(len, links.values())),
    )
    if not apply:
        return result

    db.add_all([*new_categories.values(), *new_groups.values()])
    db.flush()
    imported = {}
    for row in selected:
        source, content_type = detect_source(row.url) if row.url else ("other", "note")
        imported[row.id] = Content(
            user_id=owner, category_id=category_map[row.category_id].id if row.category_id is not None else None,
            url_normalized=data.urls.get(row.id), source=source, content_type=content_type,
            **row.model_dump(exclude={"id", "category_id"}),
        )
    db.add_all(imported.values())
    db.flush()
    db.add_all(ContentGroup(user_id=owner, content_id=imported[row_id].id, group_id=group.id)
               for row_id, assigned in links.items() for group in assigned)
    db.add(LibraryImport(user_id=owner, digest=data.digest, summary=result.model_dump(exclude={"replayed"})))
    db.commit()
    return result
