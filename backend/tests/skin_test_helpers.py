"""테스트용 피부 분석 생성 헬퍼

사진 분석은 고정 점수로 대체하고 실제 경로(POST /api/skin/analyses/debug)로 저장
동기 TestClient·비동기 httpx 클라이언트 모두 지원
"""

import inspect
from unittest.mock import patch

SCORES = dict(redness=20, brightness=70, trouble=20, uniformity=70)
PHOTO = {"file": ("face.jpg", b"photo", "image/jpeg")}


def post_skin(client, json=None):
    # app 설정 순서를 지키려고 함수 안에서 import
    from app.services import skin_analysis

    data = {k: str(v) for k, v in (json or {}).items() if v is not None}
    mock = patch.object(skin_analysis, "analyze_image_detail", return_value=(dict(SCORES), {}))
    mock.start()
    try:
        result = client.post("/api/skin/analyses/debug", data=data, files=PHOTO)
    except BaseException:
        mock.stop()
        raise
    if not inspect.isawaitable(result):
        mock.stop()
        return result

    async def wait():
        try:
            return await result
        finally:
            mock.stop()

    return wait()
