"""Versioned legacy response normalization and experimental state estimation."""
from statistics import median
from app.services.cheek_signal import capacitance_change

VERSION = 'boa-cap-response-10-v1'
ALGORITHM = 'skin-fixed-3s-v1'
CAPACITANCE_SPAN_PERCENT = 10.0


def normalize(result):
    start = result.samples[0].uptime_ms
    terminal = [s.count for s in result.samples if (s.uptime_ms-start) % 2**32 >= 2000]
    count = median(terminal)
    response = max(0.0, capacitance_change(result.baseline, count))
    from app.services.hydration_estimate import SUPPORTED_NORMALIZATIONS, estimate
    if result.normalization_version in SUPPORTED_NORMALIZATIONS:
        return dict(estimate(result.baseline, count, result.sensor_profile.reference_divider,result.normalization_version),
                    terminal_count=count, capacitance_change_percent=response)
    score = max(1, min(100, int(response / CAPACITANCE_SPAN_PERCENT * 100 + .5)))
    return dict(normalized_score=score, normalization_version=VERSION, terminal_count=count,
                scoring_status='normalized_score', unit='boa_moisture_score',
                recommendation_eligible=False, used_for_scoring=False,
                capacitance_change_percent=response)
