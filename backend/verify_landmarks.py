"""
landmark_extraction.py가 뽑은 좌표가 실제로 맞는 위치인지
사진 위에 초록 점으로 찍어서 눈으로 확인하는 스크립트.

실행 (컨테이너 안에서):
    docker compose exec api python verify_landmarks.py test_photo.jpg
"""

import sys
import cv2

from app.services.landmark_extraction import extract_landmarks_from_image


def main(image_path: str, output_path: str = "verified_output.jpg"):
    points = extract_landmarks_from_image(image_path)

    image = cv2.imread(image_path)
    for name, (x, y) in points.items():
        x, y = int(x), int(y)
        cv2.circle(image, (x, y), 5, (0, 255, 0), -1)  # 초록 점
        cv2.putText(
            image, name, (x + 6, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA,
        )

    cv2.imwrite(output_path, image)
    print(f"완료: {output_path} 에 저장됨")
    print("\n=== 추출된 좌표 ===")
    for name, (x, y) in points.items():
        print(f"{name}: ({x:.1f}, {y:.1f})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python verify_landmarks.py <사진경로> [출력경로]")
        sys.exit(1)

    image_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "verified_output.jpg"
    main(image_path, output_path)