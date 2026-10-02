"""
헤어스타일 매칭 로직
정면 사진 분석으로 얻은 얼굴형 + 사용자 선호(길이, 질감)를 받아
스타일 카탈로그에서 적합한 스타일 상위 N개를 점수순으로 반환한다.

이 모듈은 DB나 API를 전혀 모른다. 입력은 순수 파이썬 값(dict/list)이고
출력도 순수 파이썬 값이다. DB 연동은 별도의 repository/API 계층에서 담당한다.

models.hair.HairStyleCatalog는 한 스타일당 length/texture를 각각 문자열 하나로
저장하므로(배열 아님), texture_fit/length_fit은 "포함 여부"가 아니라 "일치 여부"로 계산한다.
"""

from typing import Optional, List, Dict, Any


FACE_SHAPES = ["계란형", "둥근형", "사각형", "긴형", "하트형", "다이아몬드"]

DEFAULT_WEIGHTS = {
    "face": 0.50,
    "texture": 0.25,
    "length": 0.25,
}


def face_fit_score(style: Dict[str, Any], face_shape: str) -> float:
    """스타일의 얼굴형 적합도를 반환한다. 0.0 ~ 1.0"""
    return style.get("face_fit", {}).get(face_shape, 0.0)


def texture_fit_score(style: Dict[str, Any], texture_pref: Optional[str]) -> Optional[float]:
    """질감 적합도. 선호 미선택이면 None (재정규화 대상 표시). 일치하면 1.0, 아니면 0.0."""
    if texture_pref is None:
        return None
    return 1.0 if texture_pref == style.get("texture") else 0.0


def length_fit_score(style: Dict[str, Any], length_pref: Optional[str]) -> Optional[float]:
    """길이 적합도. texture_fit_score와 동일한 규칙."""
    if length_pref is None:
        return None
    return 1.0 if length_pref == style.get("length") else 0.0


def calculate_match_score(
    face_score: float,
    texture_score: Optional[float],
    length_score: Optional[float],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    매칭 점수 = 0.5*얼굴형적합도 + 0.25*질감적합도 + 0.25*길이적합도
    선호를 선택하지 않은 항목(None)은 제외하고 나머지 가중치로 재정규화한다.
    """
    weights = weights or DEFAULT_WEIGHTS

    scores = {"face": face_score}
    if texture_score is not None:
        scores["texture"] = texture_score
    if length_score is not None:
        scores["length"] = length_score

    active_weight_sum = sum(weights[k] for k in scores)
    if active_weight_sum == 0:
        return 0.0

    weighted_total = sum(scores[k] * weights[k] for k in scores)
    return weighted_total / active_weight_sum


def recommend_hairstyles(
    face_shape: str,
    style_candidates: List[Dict[str, Any]],
    texture_pref: Optional[str] = None,
    length_pref: Optional[str] = None,
    top_n: int = 5,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    스타일 후보 목록을 받아 점수 계산 후 상위 top_n개를 반환한다.

    각 후보 style dict는 최소한 다음 키를 가지고 있어야 한다:
        style_id, name, face_fit, texture, length, asset_id, image, guide

    반환 형식:
        [{style_id, name, face_fit, texture_fit, length_fit, score,
          note, asset_id, image}, ...]
    face_fit/texture_fit/length_fit은 hair_recommendations 테이블에
    개별 컬럼으로 그대로 저장할 수 있게 세분화해서 내보낸다.
    """
    results = []
    for style in style_candidates:
        face_score = face_fit_score(style, face_shape)
        texture_score = texture_fit_score(style, texture_pref)
        length_score = length_fit_score(style, length_pref)
        final_score = calculate_match_score(face_score, texture_score, length_score, weights)

        results.append({
            "style_id": style["style_id"],
            "name": style["name"],
            "face_fit": round(face_score, 4),
            "texture_fit": round(texture_score, 4) if texture_score is not None else None,
            "length_fit": round(length_score, 4) if length_score is not None else None,
            "score": round(final_score, 4),
            "note": style.get("guide", ""),
            "asset_id": style.get("asset_id"),
            "image": style.get("image"),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]