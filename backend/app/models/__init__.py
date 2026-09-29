# Alembic autogenerate가 테이블을 인식하려면 모든 모델을 여기서 import 해야 한다
from app.models.image import Image
from app.models.cosmetic import (
    Brand,
    Product,
    Ingredient,
    ProductIngredient,
)

__all__ = [
    "Image",
    "Brand",
    "Product",
    "Ingredient",
    "ProductIngredient",
]