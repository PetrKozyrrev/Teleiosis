from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Category, Content
from app.schemas import MAX_BIGINT, CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])

CategoryId = Annotated[int, Path(gt=0, le=MAX_BIGINT)]


def get_own_category(db: DbSession, user: CurrentUser, category_id: int) -> Category:
    """Категория ищется сразу с фильтром по владельцу.
    Чужая и несуществующая выглядят одинаково: 404."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id, Category.user_id == user.id
        )
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


def commit_or_conflict(db: DbSession) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Category with this name already exists"
        )


def counts_for(db: DbSession, user: CurrentUser, category_ids: list[int]) -> dict[int, int]:
    """Сколько материалов текущего пользователя в каждой категории (одним запросом)."""
    if not category_ids:
        return {}
    rows = db.execute(
        select(Content.category_id, func.count())
        .where(Content.user_id == user.id, Content.category_id.in_(category_ids))
        .group_by(Content.category_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def to_out(category: Category, counts: dict[int, int]) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "created_at": category.created_at,
        "contents_count": counts.get(category.id, 0),
    }


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: DbSession, user: CurrentUser):
    category = Category(user_id=user.id, name=data.name)
    db.add(category)
    commit_or_conflict(db)
    db.refresh(category)
    return to_out(category, {})  # новая категория пуста


@router.get("", response_model=list[CategoryOut])
def list_categories(db: DbSession, user: CurrentUser):
    query = (
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(Category.name, Category.id)
    )
    categories = db.scalars(query).all()
    counts = counts_for(db, user, [c.id for c in categories])
    return [to_out(c, counts) for c in categories]


@router.patch("/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: CategoryId, data: CategoryUpdate, db: DbSession, user: CurrentUser
):
    category = get_own_category(db, user, category_id)
    category.name = data.name
    commit_or_conflict(db)
    db.refresh(category)
    return to_out(category, counts_for(db, user, [category.id]))


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: CategoryId, db: DbSession, user: CurrentUser):
    category = get_own_category(db, user, category_id)
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)