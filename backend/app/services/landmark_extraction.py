"""
MediaPipe Face Mesh(solutions API, mediapipe==0.10.21 기준)를 이용한
얼굴 랜드마크 추출.

face_shape_analysis.py가 요구하는 11개 포인트(REQUIRED_POINTS)를
468개 랜드마크 중 해당 인덱스를 골라 뽑아낸다.

이 모듈의 출력은 face_shape_analysis.analyze_face_shape()의 입력 형태와
정확히 일치하도록 맞춰져 있다. 즉 이 모듈 → 그 함수로 그대로 이어 붙이면 된다.

설치 버전 고정 (numpy 호환성 문제로 묶어서 설치해야 함):
    uv add "mediapipe==0.10.21" "opencv-python-headless<5"
"""

import cv2
import mediapipe as mp
import numpy as np
from typing import Dict, Tuple

Point = Tuple[float, float]

# ------------------------------------------------------------------
# 468개 랜드마크 중, 우리가 쓸 11개 포인트의 인덱스.
# (참고용 근사치: 실제 사진에 점을 찍어서 눈으로 확인 후 필요시 조정할 것 — verify_landmarks.py 참고)
# ------------------------------------------------------------------
LANDMARK_INDEX_MAP = {
    "left_eye": 133,
    "right_eye": 362,
    "forehead_left": 103,
    "forehead_right": 332,
    "cheek_left": 234,
    "cheek_right": 454,
    "jaw_left": 172,
    "jaw_right": 397,
    "top": 10,
    "chin": 152,
    "nose_base": 2,
}

_mp_face_mesh = mp.solutions.face_mesh


def extract_landmarks_from_image(image_path: str) -> Dict[str, Point]:
    """
    이미지 파일 경로를 받아 face_shape_analysis.analyze_face_shape()가
    바로 쓸 수 있는 형태(11개 키의 (x, y) 픽셀 좌표 dict)로 반환한다.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

    height, width = image.shape[:2]
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    with _mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        result = face_mesh.process(rgb_image)

    if not result.multi_face_landmarks:
        raise ValueError("얼굴을 검출하지 못했습니다. 다시 촬영해주세요.")

    face_landmarks = result.multi_face_landmarks[0].landmark

    return {
        name: (face_landmarks[idx].x * width, face_landmarks[idx].y * height)
        for name, idx in LANDMARK_INDEX_MAP.items()
    }


def extract_landmarks_from_bytes(image_bytes: bytes) -> Dict[str, Point]:
    """S3/업로드에서 받은 바이트(bytes)로 바로 처리할 때 쓰는 버전."""
    np_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("이미지 디코딩에 실패했습니다.")

    height, width = image.shape[:2]
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    with _mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        result = face_mesh.process(rgb_image)

    if not result.multi_face_landmarks:
        raise ValueError("얼굴을 검출하지 못했습니다. 다시 촬영해주세요.")

    face_landmarks = result.multi_face_landmarks[0].landmark
    return {
        name: (face_landmarks[idx].x * width, face_landmarks[idx].y * height)
        for name, idx in LANDMARK_INDEX_MAP.items()
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python landmark_extraction.py <이미지경로>")
        sys.exit(1)

    pts = extract_landmarks_from_image(sys.argv[1])
    print("=== 추출된 랜드마크 ===")
    for name, (x, y) in pts.items():
        print(f"{name}: ({x:.1f}, {y:.1f})")