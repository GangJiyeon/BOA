"""추천 규칙 계약. 파일은 시드/오프라인 검증 전용, API는 DB 규칙을 사용한다."""
from datetime import date
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.cosmetic import MetricCode

DEFAULT_RULE_VERSION = "cosmetic-rules-2026-10-05-v1"
BUNDLE_PATH = Path(__file__).resolve().parents[1] / "data" / "cosmetic_rules_v1.json"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(StrictModel):
    code: str
    title: str
    url: str
    kind: Literal["human_study", "professional_guidance"]
    access_scope: str
    summary: str
    limitations: str
    reviewed_on: date


class Rule(StrictModel):
    code: str
    metric: MetricCode
    category: str = "개선 필요"
    ingredient: str
    effect: Literal["match", "exclude", "caution"]
    status: Literal["active", "deferred"]
    match_score: int = Field(ge=0, le=1)
    hard_exclude: bool
    condition: Literal["always", "redness_opt_in"] = "always"
    usage_scope: Literal["leave_on_candidate"] = "leave_on_candidate"
    evidence_code: str
    rationale: str

    @model_validator(mode="after")
    def consistent_action(self):
        if self.match_score != (1 if self.effect == "match" else 0):
            raise ValueError("매칭 1점, 배제·주의 0점이어야 합니다.")
        if self.hard_exclude != (self.effect == "exclude"):
            raise ValueError("hard_exclude와 effect가 일치해야 합니다.")
        if self.condition == "redness_opt_in" and (self.metric != "redness" or self.effect != "exclude"):
            raise ValueError("홍조 옵션은 홍조 배제 규칙에만 적용합니다.")
        return self


class RuleBundle(StrictModel):
    version: str
    description: str
    evidence: tuple[Evidence, ...]
    rules: tuple[Rule, ...]

    @model_validator(mode="after")
    def consistent_bundle(self):
        evidence_codes = {e.code for e in self.evidence}
        if len(evidence_codes) != len(self.evidence) or len({r.code for r in self.rules}) != len(self.rules):
            raise ValueError("중복된 근거/규칙 코드")
        keys = [(r.metric, r.category, r.ingredient, r.effect) for r in self.rules]
        if len(set(keys)) != len(keys):
            raise ValueError("중복된 성분 규칙")
        if not self.rules or any(r.evidence_code not in evidence_codes for r in self.rules):
            raise ValueError("규칙 또는 연결 근거 누락")
        return self

    def fingerprint(self) -> str:
        # 규칙 순서는 효능 순위가 아니므로 정렬한 표현으로 변경 여부를 검증한다.
        normalized = self.model_copy(update={
            "evidence": tuple(sorted(self.evidence, key=lambda e: e.code)),
            "rules": tuple(sorted(self.rules, key=lambda r: r.code)),
        })
        return hashlib.sha256(normalized.model_dump_json().encode()).hexdigest()


def load_seed_bundle() -> RuleBundle:
    return RuleBundle.model_validate_json(BUNDLE_PATH.read_text(encoding="utf-8"))
