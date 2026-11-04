from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, DbSession
from app.models import Category
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


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


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: DbSession, user: CurrentUser):
    category = Category(user_id=user.id, name=data.name)
    db.add(category)
    commit_or_conflict(db)
    db.refresh(category)
    return category


@router.get("", response_model=list[CategoryOut])
def list_categories(db: DbSession, user: CurrentUser):
    query = (
        select(Category)
        .where(Category.user_id == user.id)
        .order_by(Category.name, Category.id)
    )
    return db.scalars(query).all()


@router.patch("/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: int, data: CategoryUpdate, db: DbSession, user: CurrentUser
):
    category = get_own_category(db, user, category_id)
    category.name = data.name
    commit_or_conflict(db)
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: DbSession, user: CurrentUser):
    category = get_own_category(db, user, category_id)
    db.delete(category)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)