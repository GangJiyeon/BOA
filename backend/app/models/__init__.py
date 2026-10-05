# Alembic autogenerate가 테이블을 인식하려면 모든 모델을 여기서 import 해야 한다
from app.models.image import Image
from app.models.skin import SkinAnalysis, SkinMetric, SkinMetricCategory, SkinScore
from app.models.cosmetic import (
    Brand,
    Product,
    Ingredient,
    ProductIngredient,
)
from app.models.hair import (
    FaceAnalysis,
    UserHairPreferences,
    HairStyleCatalog,
    HairRecRun,
    HairRecommendation,
)

__all__ = [
    "Image",
    "SkinAnalysis",
    "SkinMetric",
    "SkinMetricCategory",
    "SkinScore",
    "Brand",
    "Product",
    "Ingredient",
    "ProductIngredient",
    "FaceAnalysis",
    "UserHairPreferences",
    "HairStyleCatalog",
    "HairRecRun",
    "HairRecommendation",
]
from app.models.cosmetic_rule import CategoryIngredient, CosmeticRuleEvidence, CosmeticRuleSet
__all__ += ["CategoryIngredient", "CosmeticRuleEvidence", "CosmeticRuleSet"]
from app.models.cosmetic_observation import CosmeticObservationBatch, ProductIngredientObservation
__all__ += ["CosmeticObservationBatch", "ProductIngredientObservation"]
