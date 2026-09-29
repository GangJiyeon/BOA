from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Brand(Base):
    __tablename__ = "brands"

    brand_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    brand_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    brand_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("brands.brand_id"),
        nullable=False,
    )

    product_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    product_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    ingredients_raw: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    parse_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    source_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Ingredient(Base):
    __tablename__ = "ingredients"

    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    ingredient_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    name_inci: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    normalized_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )


class ProductIngredient(Base):
    __tablename__ = "product_ingredients"

    product_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("products.product_id"),
        primary_key=True,
    )

    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ingredients.ingredient_id"),
        primary_key=True,
    )

    position: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )