"""Gemini 이미지 편집 호출 (REST, 응답에서 첫 이미지만 꺼냄)"""

import base64

import httpx

from app.core.config import get_settings

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Gemini가 받는 출력 비율
ASPECT_RATIOS = {"1:1": 1.0, "2:3": 2 / 3, "3:2": 1.5, "3:4": 0.75, "4:3": 4 / 3, "4:5": 0.8, "5:4": 1.25, "9:16": 9 / 16, "16:9": 16 / 9}


class ImageGenError(Exception):
    pass


def closest_aspect(width: int, height: int) -> str:
    ratio = width / height
    return min(ASPECT_RATIOS, key=lambda k: abs(ASPECT_RATIOS[k] - ratio))


def edit_image(model: str, images: list[bytes], prompt: str, aspect: str, timeout: float = 180, size: str | None = None) -> bytes:
    """이미지(JPEG) 여러 장 + 프롬프트 → 생성 이미지 바이트, size는 출력 크기 (\"2K\" 등, 없으면 모델 기본 1K)"""
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode()}} for b in images]
    body = {
        "contents": [{"parts": [*parts, {"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}},
    }
    if size:
        body["generationConfig"]["imageConfig"]["imageSize"] = size
    try:
        res = httpx.post(
            API.format(model=model),
            json=body,
            headers={"x-goog-api-key": get_settings().gemini_api_key},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise ImageGenError(f"이미지 생성 서버 연결 실패: {e}") from e
    if res.status_code != 200:
        raise ImageGenError(f"이미지 생성 실패 ({res.status_code})")
    candidates = res.json().get("candidates") or []
    for part in (candidates[0].get("content", {}).get("parts", []) if candidates else []):
        blob = part.get("inlineData") or part.get("inline_data")
        if blob:
            return base64.b64decode(blob["data"])
    # 안전 필터 등으로 이미지 없이 끝난 경우
    raise ImageGenError("이미지 생성 결과가 비어 있습니다")
