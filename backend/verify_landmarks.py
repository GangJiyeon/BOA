"""
랜드마크 검증 스크립트.

LANDMARK_INDEX_MAP에 등록된 모든 포인트를 사진 위에 찍어서
verified_output.jpg로 저장한다. 점 위치가 실제 눈/이마/광대/턱/코
위치와 맞는지 눈으로 확인하는 용도.

사용법:
    python verify_landmarks.py <이미지경로>
"""

import sys
import cv2

from app.services.landmark_extraction import extract_landmarks_from_image, LANDMARK_INDEX_MAP

# 기존 11개 포인트(얼굴형용) vs 새로 추가한 4개 포인트(코 모양용)를
# 색으로 구분해서, 코 포인트가 제대로 찍히는지 한눈에 보이게 한다.
NOSE_POINTS = {"nose_tip", "nose_bridge_top", "nostril_left", "nostril_right"}

COLOR_FACE = (0, 255, 0)   # 초록 — 기존 얼굴형 포인트
COLOR_NOSE = (0, 0, 255)   # 빨강 — 새로 추가한 코 포인트


def main():
    if len(sys.argv) < 2:
        print("사용법: python verify_landmarks.py <이미지경로>")
        sys.exit(1)

    image_path = sys.argv[1]
    points = extract_landmarks_from_image(image_path)

    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

    print("=== 추출된 랜드마크 ===")
    for name, (x, y) in points.items():
        color = COLOR_NOSE if name in NOSE_POINTS else COLOR_FACE
        print(f"{name}: ({x:.1f}, {y:.1f})")

        cv2.circle(image, (int(x), int(y)), 4, color, -1)
        cv2.putText(
            image, name, (int(x) + 6, int(y) - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA,
        )

    missing = set(LANDMARK_INDEX_MAP) - set(points)
    if missing:
        print(f"\n경고: 추출 안 된 포인트 있음: {missing}")

    cv2.imwrite("verified_output.jpg", image)
    print("\n저장 완료: verified_output.jpg")


if __name__ == "__main__":
    main()