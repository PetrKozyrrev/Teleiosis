"""Tags and collections; shared handlers for web and /mobile/library aliases."""
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Path, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Content, ContentGroup, LibraryGroup, User
from app.routers.contents import ContentId, get_own_content
from app.schemas import MAX_BIGINT, LibraryGroupOut, LibraryGroupWrite, OrganizationOut, OrganizationUpdate

GROUP_LIMIT = 200
GroupId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


def lock_owner(db, user):
    # Serialize organization writes per owner: quota checks and delete/assign cannot race.
    # Content edits retain their existing row lock and version precondition.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).one()


def own_group(db, user, group_id, kind):
    group = db.scalar(select(LibraryGroup).where(
        LibraryGroup.id == group_id, LibraryGroup.user_id == user.id, LibraryGroup.kind == kind))
    if group is None:
        raise HTTPException(404, "Tag or collection not found")
    return group


def commit_group(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, {"code": "group_name_exists"})


def counts(db, user, kind):
    return dict(db.execute(select(ContentGroup.group_id, func.count()).join(
        LibraryGroup, LibraryGroup.id == ContentGroup.group_id).where(
            ContentGroup.user_id == user.id, LibraryGroup.user_id == user.id,
            LibraryGroup.kind == kind).group_by(ContentGroup.group_id)).all())


def group_out(group, count=0):
    return {"id": group.id, "name": group.name, "created_at": group.created_at, "contents_count": count}


def make_group_router(path: str, kind: str):
    router = APIRouter(prefix=path, tags=["organization"])

    @router.get("", response_model=list[LibraryGroupOut])
    def list_groups(db: DbSession, user: CurrentUser):
        groups = db.scalars(select(LibraryGroup).where(
            LibraryGroup.user_id == user.id, LibraryGroup.kind == kind).order_by(
                func.lower(LibraryGroup.name), LibraryGroup.id)).all()
        totals = counts(db, user, kind)
        return [group_out(group, totals.get(group.id, 0)) for group in groups]

    @router.post("", response_model=LibraryGroupOut, status_code=201)
    def create_group(data: LibraryGroupWrite, db: DbSession, user: CurrentUser):
        lock_owner(db, user)
        if db.scalar(select(func.count()).select_from(LibraryGroup).where(
                LibraryGroup.user_id == user.id, LibraryGroup.kind == kind)) >= GROUP_LIMIT:
            raise HTTPException(409, {"code": "group_limit_reached"})
        group = LibraryGroup(user_id=user.id, kind=kind, name=data.name)
        db.add(group)
        commit_group(db)
        db.refresh(group)
        return group_out(group)

    @router.patch("/{group_id}", response_model=LibraryGroupOut)
    def rename_group(group_id: GroupId, data: LibraryGroupWrite, db: DbSession, user: CurrentUser):
        lock_owner(db, user)
        group = own_group(db, user, group_id, kind)
        group.name = data.name
        commit_group(db)
        db.refresh(group)
        return group_out(group, counts(db, user, kind).get(group.id, 0))

    @router.delete("/{group_id}", status_code=204)
    def delete_group(group_id: GroupId, db: DbSession, user: CurrentUser):
        lock_owner(db, user)
        group = own_group(db, user, group_id, kind)
        members = select(ContentGroup.content_id).where(
            ContentGroup.user_id == user.id, ContentGroup.group_id == group.id)
        db.execute(update(Content).where(Content.user_id == user.id, Content.id.in_(members)).values(
            version=Content.version + 1, updated_at=func.now()))
        db.delete(group)
        db.commit()
        return Response(status_code=204)

    return router


tags_router = make_group_router("/tags", "tag")
collections_router = make_group_router("/collections", "collection")
router = APIRouter(prefix="/contents", tags=["organization"])


def organization_out(db, user, content):
    groups = db.scalars(select(LibraryGroup).join(ContentGroup, ContentGroup.group_id == LibraryGroup.id).where(
        ContentGroup.user_id == user.id, ContentGroup.content_id == content.id,
        LibraryGroup.user_id == user.id).order_by(func.lower(LibraryGroup.name), LibraryGroup.id)).all()
    return {"content_id": content.id, "version": content.version,
            "tags": [group for group in groups if group.kind == "tag"],
            "collections": [group for group in groups if group.kind == "collection"]}


@router.get("/{content_id}/organization", response_model=OrganizationOut)
def read_organization(content_id: ContentId, db: DbSession, user: CurrentUser):
    return organization_out(db, user, get_own_content(db, user, content_id))


@router.patch("/{content_id}/organization", response_model=OrganizationOut)
def change_organization(content_id: ContentId, data: OrganizationUpdate, db: DbSession, user: CurrentUser,
                        if_match: Annotated[str, Header(pattern=r'^"[1-9][0-9]{0,18}"$')]):
    lock_owner(db, user)
    content = get_own_content(db, user, content_id, lock=True)
    if content.version != int(if_match[1:-1]):
        raise HTTPException(412, {"code": "content_version_changed"})
    all_groups = db.scalars(select(LibraryGroup).where(LibraryGroup.user_id == user.id)).all()
    owned = {group.id: group.kind for group in all_groups}
    selected = {}
    # Validate everything before writing any membership.
    for field, kind in (("tag_ids", "tag"), ("collection_ids", "collection")):
        if field in data.model_fields_set:
            ids = set(getattr(data, field))
            if any(owned.get(group_id) != kind for group_id in ids):
                raise HTTPException(404, "Tag or collection not found")
            selected[kind] = ids
    existing = set(db.scalars(select(ContentGroup.group_id).where(
        ContentGroup.user_id == user.id, ContentGroup.content_id == content.id)).all())
    desired = {group_id for group_id in existing if owned[group_id] not in selected}
    desired.update(group_id for ids in selected.values() for group_id in ids)
    if desired != existing:
        db.execute(delete(ContentGroup).where(ContentGroup.user_id == user.id,
            ContentGroup.content_id == content.id, ContentGroup.group_id.in_(existing - desired)))
        db.add_all(ContentGroup(user_id=user.id, content_id=content.id, group_id=group_id)
                   for group_id in desired - existing)
        content.version += 1
        content.updated_at = func.now()
    db.commit()
    db.refresh(content)
    return organization_out(db, user, content)
