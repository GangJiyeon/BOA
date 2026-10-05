"""제품명 기반 보조 분류. 제조사 사용법 검증을 대체하지 않는다."""

import re
import unicodedata
from typing import Literal

UsageMode = Literal["leave_on_candidate", "rinse_off", "uncertain"]


def classify_usage(name: str) -> tuple[UsageMode, str]:
    name = unicodedata.normalize("NFKC", name).casefold()
    compact = re.sub(r"[\s_-]+", "", name)
    if not compact:
        return "uncertain", "제품명이 없어 사용 방식과 부위를 추정할 수 없음"
    rinse = any(token in compact for token in (
        "워시오프", "washoff", "rinseoff", "클렌저", "클렌징", "스크럽",
        "페이스워시", "페이셜워시", "폼클렌", "세안", "샴푸", "바디워시",
        "facewash", "facialwash", "cleanser", "cleansing", "scrub", "shampoo", "bodywash",
    ))
    mixed = bool(re.search(r"증정|기획|세트|\+", name))
    if rinse and mixed:
        return "uncertain", "씻어내는 구성품과 기획·증정 표기가 함께 있어 본품 사용 방식 확인 필요"
    if rinse:
        return "rinse_off", "제품명에 워시오프·세정·스크럽 표기"
    if "필링" in compact or "peeling" in compact:
        return "uncertain", "필링 표기만으로 접촉 시간과 씻어내는지 확인 불가"
    # 화장품 카테고리는 사용 부위가 아니다. 브랜드명 '더바디샵', '핸드타올',
    # '헤어핀' 같은 단어까지 배제하지 않도록 제품 유형 표현만 검사한다.
    body = any(t in compact for t in ("바디로션", "바디크림", "바디밀크", "바디오일",
                                      "bodylotion", "bodycream", "bodymilk", "bodyoil"))
    face_body = any(t in compact for t in ("페이스&바디", "페이스앤바디", "얼굴&바디",
                                           "face&body", "faceandbody"))
    if body and not face_body:
        return "uncertain", "바디용 표기가 있어 얼굴 추천 적용 범위 확인 필요"
    localized = any(t in compact for t in ("핸드크림", "핸드로션", "풋크림", "풋로션",
        "발크림", "립밤", "립마스크", "두피세럼", "두피토닉", "헤어세럼", "헤어에센스",
        "handcream", "handlotion", "footcream", "footlotion", "lipbalm", "lipmask",
        "scalpserum", "scalptonic", "hairserum"))
    if localized:
        return "uncertain", "손·발·입술·모발 등 국소 사용 표기가 있어 얼굴 추천 적용 범위 확인 필요"
    eye = any(t in compact for t in ("아이크림", "아이세럼", "아이밤", "eyecream", "eyeserum", "eyebalm"))
    eye_for_face = bool(re.search(r"(?:아이크림|아이세럼|아이밤|eyecream|eyeserum|eyebalm)(?:포페이스|forface)", compact))
    if eye and not eye_for_face:
        return "uncertain", "눈가용 표기가 있어 얼굴 전체 지표에 대한 추천 적용 범위 확인 필요"
    return "leave_on_candidate", "기초 제품 종류와 제품명 기반 추정 · 제조사 사용법 미확인"
