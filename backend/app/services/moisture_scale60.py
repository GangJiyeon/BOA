"""BOA integer 0..60 index; experimental PNJ bands, not skin water percent.

PNJ classifies the manufacturer's *truncated integer*. Thus transitions occur
at continuous responses 13, 23, 28, 40, 46 (not 12, 22, 27, 39, 45).
Floor within each destination band preserves those classifications exactly.
"""
import math

LEGACY_VERSION = 'boa-moisture-60-v1'
VERSION = 'boa-moisture-60-sqrt-v2'
SUPPORTED_VERSIONS = (LEGACY_VERSION, VERSION)
SOURCE_BREAKS = (0, 13, 23, 28, 40, 46, 100)
LEVEL_LABELS = ('매우 부족', '부족', '보통 중 낮음', '보통', '보통 중 높음', '매우 높음')


def score_from_response(response: float, version: str = VERSION) -> int:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError('unsupported 0..60 scale version')
    if not math.isfinite(response) or not 0 <= response <= 100:
        raise ValueError('sensor response must be finite and within 0..100')
    # Only absorb floating point noise at integer source boundaries.
    nearest = round(response)
    if abs(response - nearest) < 1e-9:
        response = float(nearest)
    if response == 100:
        return 60
    band = next(i for i in range(6) if response < SOURCE_BREAKS[i + 1])
    lo, hi = SOURCE_BREAKS[band:band + 2]
    fraction = (response - lo) / (hi - lo)
    if version == VERSION:
        fraction = math.sqrt(fraction)
    within = min(9, math.floor(10 * fraction))
    return band * 10 + within


def classification(score: int) -> dict:
    if type(score) is not int or not 0 <= score <= 60:
        raise ValueError('moisture score must be an integer within 0..60')
    level = min(6, score // 10 + 1)
    state = 'low' if level <= 2 else 'normal' if level <= 5 else 'sufficient'
    return dict(moisture_level=level, moisture_level_label=LEVEL_LABELS[level - 1],
                score_max=60, estimated_state=state,
                estimated_state_label={'low': '부족', 'normal': '보통', 'sufficient': '충분'}[state],
                estimation_category={'low': '개선 필요', 'normal': '보통', 'sufficient': '양호'}[state])
