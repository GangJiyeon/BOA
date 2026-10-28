"""Uncalibrated FDC2112 telemetry, deliberately separate from skin scores."""
from datetime import datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MoistureMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal[1] = 1
    source: Literal["ble_sensor", "ble_simulation", "mock"]
    status: Literal["valid", "sensor_error", "not_ready"]
    raw_value: int | None = Field(default=None, strict=True, ge=0, le=4095)
    unit: Literal["fdc2112_count"] = "fdc2112_count"
    sequence: int = Field(strict=True, ge=0, le=65535)
    device_uptime_ms: int = Field(strict=True, ge=0, le=4294967295)
    received_at: AwareDatetime

    @model_validator(mode="after")
    def valid_raw(self):
        if (self.status == "valid") != (self.raw_value is not None):
            raise ValueError("valid requires raw_value; error/not_ready requires null")
        return self


class MoistureSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: int | None = Field(default=None, strict=True, gt=0)
    measurement: MoistureMeasurement


class MoistureReceipt(MoistureSubmission):
    server_received_at: datetime
    calibration_status: Literal["uncalibrated"] = "uncalibrated"
    persisted: Literal[False] = False
    used_for_scoring: Literal[False] = False


from uuid import UUID
import math


class FreshSample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(strict=True, ge=0, le=65535)
    uptime_ms: int = Field(strict=True, ge=0, le=4294967295)
    count: int = Field(strict=True, ge=0, le=4095)


class DiscardedSample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: int = Field(strict=True,ge=0,le=65535)
    uptime_ms: int = Field(strict=True,ge=0,le=4294967295)
    status: Literal['not_ready','sensor_error']
    warning_flags: int = Field(strict=True,ge=0,le=61440)
    diagnostic_count: int | None = Field(default=None,strict=True,ge=0,le=4095)


class SensorProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reference_divider: Literal[11,22,44]
    output_gain: Literal[16]
    offset: Literal[170]
    sensor_divider: Literal[2]
    verified: Literal[True]
    drive_current_code: int | None = Field(default=None,strict=True,ge=0,le=31)


class CompletedMoisture(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    measurement_id: UUID
    algorithm_version: Literal['cheek-auto-v1', 'cheek-auto-v2', 'skin-auto-v3', 'skin-auto-v4', 'skin-auto-v5','skin-auto-v6','skin-fixed-3s-v1']
    site: Literal['left_cheek', 'skin']
    measured_at: AwareDatetime
    baseline: int = Field(strict=True, ge=1, le=4095)
    samples: list[FreshSample] = Field(min_length=25, max_length=50)
    contact_threshold: float = Field(gt=0, le=20)
    release_threshold: float = Field(gt=0, le=10)

    air_samples: list[FreshSample] | None = Field(default=None, min_length=16, max_length=64)
    window_end_uptime_ms: int | None = Field(default=None, strict=True, ge=0, le=4294967295)
    normalization_version: str | None = None
    sensor_profile: SensorProfile | None = None
    discarded_samples: list[DiscardedSample] | None = Field(default=None,max_length=35)

    def statistics(self):
        counts = [s.count for s in self.samples]
        mean = sum(counts) / len(counts)
        percentages = [(self.baseline - n) * 100 / self.baseline for n in counts]
        avg = sum(percentages) / len(percentages)
        return dict(relative_percent=round(max(0, min(100, (self.baseline - mean) * 100 / self.baseline)), 2),
                    discarded_sample_count=len(self.discarded_samples or []),
                    warning_sample_count=sum(s.warning_flags!=0 for s in self.discarded_samples or []),
                    mean_count=round(mean, 4), sample_count=len(counts),
                    duration_ms=3000 if self.algorithm_version=='skin-fixed-3s-v1' else (self.samples[-1].uptime_ms - self.samples[0].uptime_ms) % 2**32,
                    stddev_percent=round(math.sqrt(sum((x-avg)**2 for x in percentages) / len(percentages)), 4),
                    range_percent=round(max(percentages)-min(percentages), 4))

    @model_validator(mode='after')
    def validate_window(self):
        modern = self.algorithm_version in ('skin-auto-v3','skin-auto-v4','skin-auto-v5','skin-auto-v6','skin-fixed-3s-v1')
        if modern:
            from app.services.cheek_signal import detection_threshold
            if self.site != 'skin' or self.air_samples is None:
                raise ValueError('skin v3 requires air reference samples')
            if any(s.count <= 1 or s.count >= 4094 for s in self.samples + self.air_samples):
                raise ValueError('measurement is at the output rail')
            air=self.air_samples
            for before, after in zip(air,air[1:]):
                if not 1 <= (after.sequence-before.sequence)%65536 <= 4 or not 50 <= (after.uptime_ms-before.uptime_ms)%2**32 <= 350:
                    raise ValueError('invalid air reference sequence')
            if not 2000 <= (air[-1].uptime_ms-air[0].uptime_ms)%2**32 <= 5000:
                raise ValueError('invalid air reference duration')
            if not 0 < (self.samples[0].uptime_ms-air[-1].uptime_ms)%2**32 <= 0x7fffffff:
                raise ValueError('air reference must precede contact')
            if any(abs(self.baseline-x.count)*100/self.baseline > 2 for x in air):
                raise ValueError('air reference does not match baseline')
            expected=detection_threshold(self.baseline,[x.count for x in air])
            if abs(self.contact_threshold-expected)>1e-6:
                raise ValueError('contact threshold does not match air noise')
        elif self.site != 'left_cheek' or self.air_samples is not None or self.contact_threshold < 2:
            raise ValueError('legacy measurement format mismatch')
        if abs(self.release_threshold - self.contact_threshold / 2) > 0.000001:
            raise ValueError('release threshold must match algorithm version')
        for before, after in zip(self.samples, self.samples[1:]):
            if not 1 <= (after.sequence-before.sequence) % 65536 <= 4:
                raise ValueError('duplicate or reordered samples')
            if not 50 <= (after.uptime_ms-before.uptime_ms) % 2**32 <= 350:
                raise ValueError('invalid sample interval')
        stats = self.statistics()
        if self.algorithm_version == 'skin-fixed-3s-v1':
            from app.services.moisture_normalization import VERSION
            from app.services.hydration_estimate import SUPPORTED_NORMALIZATIONS, estimate
            start=self.samples[0].uptime_ms
            if self.normalization_version not in (VERSION, *SUPPORTED_NORMALIZATIONS) or self.window_end_uptime_ms is None or (self.window_end_uptime_ms-start)%2**32 != 3000:
                raise ValueError('fixed measurement must specify the 3-second window and normalization')
            offsets=[(s.uptime_ms-start)%2**32 for s in self.samples]
            discarded=self.discarded_samples or []
            if any((s.uptime_ms-start)%2**32>3000 or s.warning_flags&0x0fff or (s.status=='not_ready' and s.warning_flags) for s in discarded):
                raise ValueError('invalid discarded sample metadata')
            if any((s.uptime_ms-start)%2**32>=2000 and s.status=='sensor_error' for s in discarded):
                raise ValueError('terminal sensor errors cannot be censored into a hydration estimate')
            combined=self.samples+discarded
            if len({s.sequence for s in combined})!=len(combined) or len({s.uptime_ms for s in combined})!=len(combined):
                raise ValueError('discarded samples must not duplicate valid samples')
            if offsets[-1] < 2650 or any(x>3000 for x in offsets):
                raise ValueError('samples must cover the fixed window without extending it')
            terminal=[s.count for s,x in zip(self.samples,offsets) if x>=2000]
            from statistics import median
            if len(terminal)<5 or (self.baseline-median(terminal))*100/self.baseline <= self.release_threshold:
                raise ValueError('skin contact was not maintained')
            if self.normalization_version in SUPPORTED_NORMALIZATIONS:
                if self.sensor_profile is None:
                    raise ValueError('hydration estimation requires the device-reported verified profile')
                estimate(self.baseline, median(terminal), self.sensor_profile.reference_divider)
            return self
        if not 3000 <= stats['duration_ms'] <= 3350:
            raise ValueError('measurement duration must be a complete 3-second window')
        values = [(self.baseline-s.count)*100/self.baseline for s in self.samples]
        avg = sum(values)/len(values)
        if max(values)-min(values) > 3 or math.sqrt(sum((v-avg)**2 for v in values)/len(values)) > 1.2:
            raise ValueError('unstable measurement')
        if min(values) <= self.release_threshold:
            raise ValueError('contact was lost during measurement')
        if self.algorithm_version in ('cheek-auto-v2', 'skin-auto-v3', 'skin-auto-v4','skin-auto-v5','skin-auto-v6'):
            from app.services.cheek_signal import signal_statistics
            if self.baseline <= 30:
                raise ValueError('unsupported air baseline')
            quality = signal_statistics(self.baseline, [s.count for s in self.samples], modern=modern, guarded=self.algorithm_version in ('skin-auto-v4','skin-auto-v5','skin-auto-v6'), stationary=self.algorithm_version == 'skin-auto-v6')
            if quality['capacitance_range_pp'] > 2 or quality['capacitance_stddev_pp'] > 0.75 or quality['capacitance_drift_pp'] > 1:
                raise ValueError('unstable capacitance signal')
            if self.algorithm_version in ('skin-auto-v4','skin-auto-v5','skin-auto-v6') and quality['capacitance_drift_pp'] > quality['drift_limit_pp'] + 1e-9:
                raise ValueError('signal drift exceeds response-relative limit')
            if self.algorithm_version in ('skin-auto-v5','skin-auto-v6') and quality['resolution_limited']:
                raise ValueError('insufficient sensor response; measurement not confirmed')
        return self


class CompletedSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis_id: int = Field(strict=True, gt=0)
    result: CompletedMoisture


class CompletedReceipt(BaseModel):
    discarded_sample_count: int = 0
    warning_sample_count: int = 0
    estimated_state: Literal['low','normal','sufficient'] | None = None
    estimated_state_label: str | None = None
    estimation_version: str | None = None
    estimation_basis: str | None = None
    validation_level: str | None = None
    manufacturer_response: float | None = None
    manufacturer_index: int | None = None
    normalized_score: int | None = Field(default=None, strict=True, ge=0, le=100)
    score_max: int = Field(default=100, strict=True, ge=1, le=100)
    moisture_level: int | None = Field(default=None, strict=True, ge=1, le=6)
    moisture_level_label: str | None = None
    normalization_version: str | None = None
    terminal_count: float | None = None
    measurement_id: str
    analysis_id: int
    site: Literal['left_cheek', 'skin']
    measured_at: AwareDatetime
    algorithm_version: Literal['cheek-auto-v1', 'cheek-auto-v2', 'skin-auto-v3', 'skin-auto-v4', 'skin-auto-v5','skin-auto-v6','skin-fixed-3s-v1']
    relative_percent: float
    mean_count: float
    baseline: int
    sample_count: int
    duration_ms: int
    stddev_percent: float
    range_percent: float
    persisted: Literal[True] = True
    used_for_scoring: bool = False
    scoring_status: str = 'calibration_missing'
    calibration_version: str | None = None
    calibration_sha256: str | None = None
    reference_value: float | None = None
    reference_unit: str | None = None
    reference_device: str | None = None
    calibrated_score: int | None = Field(default=None, ge=0, le=100)
    score_category: str | None = None
    score_metric_name: str | None = None
    capacitance_change_percent: float | None = None
    capacitance_range_pp: float | None = None
    capacitance_stddev_pp: float | None = None
    capacitance_drift_pp: float | None = None
    experimental_index: float | None = None
    index_saturated: bool = False
    recommendation_eligible: bool = False
    response_lower: float | None = None
    response_upper: float | None = None
    response_step_pp: float | None = None
    resolution_limited: bool = False
    drift_limit_pp: float | None = None
    signal_policy: str | None = None
    unit: Literal['relative_moisture_percent', 'capacitance_contact_fraction_percent', 'boa_moisture_score'] = 'relative_moisture_percent'

    @model_validator(mode='after')
    def validate_score60_contract(self):
        from app.services.moisture_scale60 import SUPPORTED_VERSIONS, classification
        if self.normalization_version in SUPPORTED_VERSIONS:
            if self.normalized_score is None:
                raise ValueError('0..60 receipt requires the canonical score')
            expected = classification(self.normalized_score)
            for key in ('score_max', 'moisture_level', 'moisture_level_label', 'estimated_state'):
                if getattr(self, key) != expected[key]:
                    raise ValueError('0..60 score and six-level classification must agree')
            if self.used_for_scoring and self.score_category != expected['estimation_category']:
                raise ValueError('0..60 score and recommendation category must agree')
        return self
