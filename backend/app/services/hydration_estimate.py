"""Experimental adaptation of PNJ 2023's Moisture click example.

The published bands are a research prior, NOT validated BOA hydration cutoffs.
The 0..60 versions derive state from the final score while preserving source
band membership. Historical versions keep their original presentation rules.
"""
import math
from app.services.moisture_scale60 import SUPPORTED_VERSIONS as SCORE60_VERSIONS, score_from_response, classification

VERSION = 'hydration-estimate-pnj-2023-v1'
DISPLAY_VERSION = 'boa-capacitance-display-v2'
SUPPORTED_NORMALIZATIONS = (VERSION, DISPLAY_VERSION, *SCORE60_VERSIONS)
REFERENCE_DIVIDER = 11  # legacy manufacturer driver: 0x2001 | 0x000A = 0x200B
CATEGORY = {'low': '개선 필요', 'normal': '보통', 'sufficient': '양호'}
LABEL = {'low': '부족', 'normal': '보통', 'sufficient': '충분'}


def classify_response(response: float) -> str:
    """Versioned experimental prior; never reads a UI score."""
    index=math.floor(response+1e-9)
    return 'low' if index<=22 else 'normal' if index<=45 else 'sufficient'


def display_score(response: float, state: str) -> int:
    """Presentation only. Changing this function must not change care policy."""
    lo,hi,start,end={'low':(0,23,1,33),'normal':(23,46,34,66),'sufficient':(46,100,67,100)}[state]
    return max(start,min(end,math.floor(start+(end-start)*(response-lo)/(hi-lo)+.5)))


def estimate(baseline: int, count: float, divider: int, normalization_version: str = VERSION) -> dict:
    if divider not in (11, 22, 44) or not 0 < count < baseline <= 4095:
        raise ValueError('unsupported sensor profile or non-contact response')
    # Refer all raw values to gain16 / OFFSET170 / FIN2 / effective reference divider11. The legacy driver ORs bit0 into its x10 argument.
    air_ref = (baseline + 170) * REFERENCE_DIVIDER / divider - 170
    contact_ref = (count + 170) * REFERENCE_DIVIDER / divider - 170
    if air_ref <= 0 or contact_ref < 0:
        raise ValueError('outside the published example representation')
    response = max(0.0, min(100.0, 100 * (air_ref-contact_ref) / air_ref))
    # PNJ's example classifies uint8_t manufacturer output (truncated percent).
    index = math.floor(response + 1e-9)
    state = classify_response(response)
    if normalization_version not in SUPPORTED_NORMALIZATIONS:
        raise ValueError('unsupported presentation scale')
    score = (max(1,min(100,math.floor(1000*((baseline+170)**2/(count+170)**2-1)+.5)))
             if normalization_version == DISPLAY_VERSION else display_score(response,state))
    result = dict(estimated_state=state, estimated_state_label=LABEL[state],
                estimation_category=CATEGORY[state], normalized_score=score,
                normalization_version=normalization_version, estimation_version=VERSION,
                estimation_basis='pnj_2023_example_adapted', validation_level='experimental_unvalidated',
                manufacturer_response=response, manufacturer_index=index,
                scoring_status='experimental_estimate', unit='boa_moisture_score',
                used_for_scoring=False, recommendation_eligible=False)

    if normalization_version in SCORE60_VERSIONS:
        score = score_from_response(response, normalization_version)
        result.update(classification(score), normalized_score=score,
                      estimation_version=normalization_version, unit='boa_moisture_score',
                      estimation_basis='pnj_integer_bands_adapted_0_60')
    return result
