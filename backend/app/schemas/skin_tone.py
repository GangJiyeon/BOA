"""피부톤 측정·메이크업 색 계열 추천 응답 스키마."""

from pydantic import BaseModel


class TonePalette(BaseModel):
    tone_name: str          # 예: "밝은 웜톤"
    cushion: str            # 쿠션 호수 범위 안내 (정확한 호수가 아님)
    lip: list[str]          # 립 색 계열
    blush: list[str]        # 블러셔 색 계열
    eye: list[str]          # 아이섀도 색 계열
    point: str              # 한 줄 설명


class SkinToneRead(BaseModel):
    brightness_level: str   # bright | medium | deep
    brightness_label: str   # 밝은 편 | 중간 | 어두운 편
    undertone: str          # warm | neutral | cool
    undertone_label: str    # 웜 | 뉴트럴 | 쿨
    confidence: str         # high | low
    palette: TonePalette
    notices: list[str]      # 참고용 안내 문구 (화면에 그대로 노출)
    raw: dict               # 원시 측정값 (L*, b*, ITA°, h° 등) — 임계값 조정용
