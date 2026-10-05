"""화장품 추천 미리보기. 입력/출력만 정의하며 DB를 변경하지 않는다."""

from typing import Annotated, Literal

from app.services.cosmetic_usage import UsageMode

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricCode = Literal["moisture", "redness", "brightness", "trouble", "uniformity"]
RankingMode = Literal["metric_count", "concern_groups", "explicit_priority"]
ProductCategory = Literal["moisturizer", "serum", "toner"]
Score = Annotated[int, Field(strict=True, ge=0, le=100)]


class SkinScoresInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moisture: Score | None = None
    redness: Score
    brightness: Score
    trouble: Score
    uniformity: Score


class AnalysisMetricScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_code: MetricCode
    metric_name: str
    score: Score
    category_name: str
    higher_is_better: Annotated[bool, Field(strict=True)]


class CosmeticPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: SkinScoresInput | Annotated[list[AnalysisMetricScore], Field(min_length=4, max_length=5)]
    score_semantics: Literal["photo_v1", "development_assumption"] = "photo_v1"
    category: ProductCategory | None = None
    ranking_policy: RankingMode = "metric_count"
    priority_metric: MetricCode | None = None
    tie_group: Annotated[str, Field(pattern=r"^g-[1-9][0-9]*$", max_length=32)] | None = None
    tie_offset: Annotated[int, Field(strict=True, ge=0)] = 0
    snapshot_token: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    # 높은 홍조 점수에서 적용하는 보수적인 프로젝트 필터. 질환 진단이 아님.
    avoid_redness_triggers: bool = True
    excluded_ingredients: list[Annotated[str, Field(min_length=1, max_length=255)]] = Field(
        default_factory=list, max_length=30
    )

    @property
    def normalized_scores(self) -> SkinScoresInput:
        if isinstance(self.scores, SkinScoresInput):
            return self.scores
        return SkinScoresInput.model_validate({s.metric_code: s.score for s in self.scores})

    @model_validator(mode="after")
    def validate_analysis_scores(self):
        if isinstance(self.scores, list):
            codes = [s.metric_code for s in self.scores]
            if len(codes) != len(set(codes)):
                raise ValueError("중복된 피부 지표입니다.")
            self.normalized_scores  # 필수 사진 지표 4개 검증; 수분 미측정은 None
            if self.score_semantics != "photo_v1":
                raise ValueError("피부 분석 배열은 photo_v1 의미로만 처리합니다.")
        return self

    @model_validator(mode="after")
    def validate_priority_policy(self):
        if (self.tie_group is None) != (self.snapshot_token is None) or (self.tie_group is None and self.tie_offset):
            raise ValueError("더보기에는 그룹과 결과 토큰이 함께 필요합니다.")
        if (self.ranking_policy == "explicit_priority") != (self.priority_metric is not None):
            raise ValueError("explicit_priority 정책에서만 우선 고민을 반드시 지정해야 합니다.")
        return self


class MetricAssessment(BaseModel):
    code: MetricCode
    name: str
    score: int
    category: str
    needs_improvement: bool


class RuleExplanation(BaseModel):
    rule_code: str
    ingredient: str
    effect: str
    evidence_url: str
    evidence_summary: str
    limitations: str
    rationale: str


class MatchInterpretation(BaseModel):
    match_basis: str
    metric_assumption: str
    assumption_status: Literal["development_assumption"] = "development_assumption"
    unverified_items: list[str]
    product_efficacy_verified: Literal[False] = False


class IngredientMatch(BaseModel):
    metric_code: MetricCode
    metric_name: str
    ingredients: list[str]
    evidence_urls: list[str]
    rule_details: list[RuleExplanation]
    interpretation: MatchInterpretation


class SharedEvidenceGroup(BaseModel):
    evidence_url: str
    metric_codes: list[MetricCode]
    explanation: str = "같은 근거를 여러 지표에 연결했습니다. 서로 독립된 효과가 입증됐다는 뜻이 아닙니다."


class CosmeticRecommendationItem(BaseModel):
    rank: int
    product_id: int
    product_name: str
    brand_name: str
    category: str
    image_url: str | None
    source_url: str | None
    match_count: int
    matched_group_count: int = Field(default=0, ge=0)
    priority_matched: bool = False
    # 전체 후보 중 선택한 정책의 정렬 키(ID 제외)가 같은 수. 본인 포함, 품질 동등성 아님.
    ranking_tie_count: int = Field(default=1, ge=1)
    ranking_group: str = ""
    matches: list[IngredientMatch]
    shared_evidence_groups: list[SharedEvidenceGroup] = Field(default_factory=list)
    recommendation_reason: str
    bundle_suspected: bool
    usage_mode: UsageMode
    usage_basis: str


class RecommendationStats(BaseModel):
    total_products: int = 0
    unsupported_category: int = 0
    incomplete_ingredients: int = 0
    excluded_by_usage: int = 0
    excluded_by_ingredient: int = 0
    no_matching_metric: int = 0
    eligible_products: int = 0


class RankingTieGroup(BaseModel):
    key: str
    total: int
    next_offset: int | None


class CosmeticPreviewResponse(BaseModel):
    score_semantics: Literal["photo_v1", "development_assumption"] = "photo_v1"
    snapshot_token: str = ""
    tie_groups: list[RankingTieGroup] = Field(default_factory=list)
    engine_version: str
    rule_version: str
    ranking_policy: RankingMode = "metric_count"
    ranking_policy_version: str = "cosmetic-ranking-v1"
    ranking_basis: str = "매칭 지표 수 → 세트 의심 후순위 → 제품 ID"
    priority_metric: MetricCode | None = None
    explanation_version: str = "cosmetic-explanations-v1"
    score_basis: str = "개선 필요로 판정된 지표 중 성분 규칙과 매칭된 지표 수"
    target_count: int
    scorable_target_count: int
    deferred_metrics: list[MetricCode]
    assessments: list[MetricAssessment]
    missing_metrics: list[MetricCode]
    applied_exclusions: list[str]
    exclusion_details: list[RuleExplanation]
    recommendations: list[CosmeticRecommendationItem]
    stats: RecommendationStats
    notices: list[str]
    empty_reason: str | None = None
