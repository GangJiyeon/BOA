"""ERD CATEGORY_INGREDIENT를 버전·근거·보류 상태와 함께 구현한다."""
from datetime import date

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, ForeignKeyConstraint, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class CosmeticRuleSet(Base):
    __tablename__ = "cosmetic_rule_sets"
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))


class CosmeticRuleEvidence(Base):
    __tablename__ = "cosmetic_rule_evidence"
    rule_version: Mapped[str] = mapped_column(ForeignKey("cosmetic_rule_sets.version"), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40))
    access_scope: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    reviewed_on: Mapped[date] = mapped_column(Date)


class CategoryIngredient(Base):
    __tablename__ = "category_ingredients"
    __table_args__ = (
        UniqueConstraint("rule_version", "category_id", "ingredient_id", "effect", name="uq_category_ingredient_rule"),
        ForeignKeyConstraint(["rule_version", "evidence_code"], ["cosmetic_rule_evidence.rule_version", "cosmetic_rule_evidence.code"]),
        CheckConstraint("status IN ('active', 'deferred')", name="rule_status"),
        CheckConstraint("effect IN ('match', 'exclude', 'caution')", name="rule_effect"),
        CheckConstraint("(effect = 'match' AND match_score = 1) OR (effect <> 'match' AND match_score = 0)", name="rule_score"),
        CheckConstraint("(effect = 'exclude' AND hard_exclude) OR (effect <> 'exclude' AND NOT hard_exclude)", name="rule_exclusion"),
        CheckConstraint("condition IN ('always', 'redness_opt_in')", name="rule_condition"),
        CheckConstraint("usage_scope = 'leave_on_candidate'", name="rule_usage"),
    )
    rule_version: Mapped[str] = mapped_column(ForeignKey("cosmetic_rule_sets.version"), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("skin_metric_categories.id"), index=True)
    ingredient_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ingredients.ingredient_id"), index=True)
    effect: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    match_score: Mapped[int] = mapped_column(SmallInteger)
    hard_exclude: Mapped[bool] = mapped_column(Boolean)
    condition: Mapped[str] = mapped_column(String(30))
    usage_scope: Mapped[str] = mapped_column(String(40))
    evidence_code: Mapped[str] = mapped_column(String(80))
    rationale: Mapped[str] = mapped_column(Text)
