"""API 에러 코드.

프론트엔드가 메시지 문자열이 아닌 코드로 분기할 수 있게 한다.
메시지는 다듬어도 코드는 바뀌지 않으므로, 문구 수정이 프론트를 깨뜨리지 않는다.
"""


class ErrorCode:
    # 사진 입력
    IMAGE_EMPTY = "IMAGE_EMPTY"                  # 파일이 비어 있음
    IMAGE_UNREADABLE = "IMAGE_UNREADABLE"        # 형식 미지원 또는 손상
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"  # jpeg/png/webp 외
    IMAGE_TOO_DARK = "IMAGE_TOO_DARK"            # 노출 부족
    IMAGE_TOO_BRIGHT = "IMAGE_TOO_BRIGHT"        # 노출 과다

    # 얼굴 인식 — 재촬영 안내가 필요한 경우
    FACE_NOT_FOUND = "FACE_NOT_FOUND"            # 얼굴을 찾지 못함
    FACE_TOO_SMALL = "FACE_TOO_SMALL"            # 얼굴이 기준보다 작게 찍힘
    FACE_OUT_OF_FRAME = "FACE_OUT_OF_FRAME"      # 얼굴이 화면 밖으로 잘림
    SKIN_AREA_TOO_SMALL = "SKIN_AREA_TOO_SMALL"  # 가려짐 등으로 피부 영역 부족

    # 입력값
    INVALID_MOISTURE_INPUT = "INVALID_MOISTURE_INPUT"
    INVALID_SCORE = "INVALID_SCORE"
    MISSING_METRIC = "MISSING_METRIC"
    UNKNOWN_METRIC = "UNKNOWN_METRIC"

    # 서버 상태 — 사용자가 아니라 운영자가 조치해야 하는 경우
    SEED_MISSING = "SEED_MISSING"                # 지표/구간 기준 데이터 없음
    CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"    # 점수에 맞는 구간이 없음
    CONFIG_INVALID = "CONFIG_INVALID"            # 정규화 구간 설정 오류

    # 조회
    IMAGE_NOT_FOUND = "IMAGE_NOT_FOUND"
    ANALYSIS_NOT_FOUND = "ANALYSIS_NOT_FOUND"
