"""Deployment-owned calibration. No default coefficients or extrapolation.

A reviewed profile is a project decision, not a claim of clinical validation.
The profile maps response to a reference-device reading, then to BOA score.
"""
import hashlib
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.config import get_settings


class Point(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float
    y: float


class CheekProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    version: str = Field(min_length=1, max_length=80)
    status: Literal['draft', 'reviewed']
    site: Literal['left_cheek']
    algorithm_version: Literal['cheek-auto-v1']
    reference_device: str = Field(min_length=1)
    reference_unit: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    score_basis: str = Field(min_length=1)
    # Applicable air-count range must come from calibration measurements.
    baseline_min: int = Field(ge=1, le=4095)
    baseline_max: int = Field(ge=1, le=4095)
    response_to_reference: list[Point] = Field(min_length=2)
    reference_to_score: list[Point] = Field(min_length=2)

    @model_validator(mode='after')
    def check_curve(self):
        if self.baseline_min > self.baseline_max:
            raise ValueError('invalid baseline range')
        for curve in (self.response_to_reference, self.reference_to_score):
            if any(b.x <= a.x or b.y <= a.y for a,b in zip(curve,curve[1:])):
                raise ValueError('calibration anchors must increase strictly')
        if any(not 0 <= p.x <= 100 for p in self.response_to_reference):
            raise ValueError('response must be within 0..100')
        if any(not 0 <= p.y <= 100 for p in self.reference_to_score):
            raise ValueError('BOA scores must be within 0..100')
        return self


def interpolate(points, value):
    for a,b in zip(points, points[1:]):
        if a.x <= value <= b.x:
            return a.y + (value-a.x)*(b.y-a.y)/(b.x-a.x)
    return None


def convert(result, relative):
    path = get_settings().moisture_calibration_profile
    if not path:
        return {'scoring_status': 'calibration_missing'}
    try:
        raw = Path(path).read_bytes()
        profile = CheekProfile.model_validate_json(raw)
    except (OSError, ValueError):
        return {'scoring_status': 'calibration_invalid'}
    provenance = dict(calibration_version=profile.version,
                      calibration_sha256=hashlib.sha256(raw).hexdigest())
    if profile.status != 'reviewed':
        return dict(scoring_status='calibration_unreviewed', **provenance)
    if result.site != profile.site or result.algorithm_version != profile.algorithm_version:
        return dict(scoring_status='calibration_incompatible', **provenance)
    if not profile.baseline_min <= result.baseline <= profile.baseline_max:
        return dict(scoring_status='outside_calibration_range', **provenance)
    reference = interpolate(profile.response_to_reference, relative)
    score = None if reference is None else interpolate(profile.reference_to_score, reference)
    if score is None:
        return dict(scoring_status='outside_calibration_range', **provenance)
    return dict(scoring_status='ready', reference_value=reference,
                reference_unit=profile.reference_unit, reference_device=profile.reference_device,
                calibrated_score=int(score+0.5), **provenance)
