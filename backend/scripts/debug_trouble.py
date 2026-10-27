"""트러블 점수 진단 스크립트.

사진 한 장을 실제 분석 로직(app/services/skin_analysis.py)과 같은 순서로 처리하고,
트러블로 잡힌 픽셀이 어디에 있는지 이미지로 저장한다.

사용법 (backend 폴더에서)
    docker compose exec api python scripts/debug_trouble.py photos/me.jpg
    → photos/me_trouble.png 생성 + 수치 출력

오버레이 색
    초록 윤곽 : 분석에 쓰인 피부 영역 (이마·양볼·코·턱 패치)
    노랑      : 임계값은 넘었지만 크기가 작아 노이즈로 버려진 픽셀
    보라      : 피부 영역 가장자리에 걸쳐 경계 효과로 제외된 덩어리
    빨강      : 최종 트러블로 집계된 덩어리
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# backend 폴더를 import 경로에 추가 (다른 scripts와 같은 방식)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import skin_analysis as sa  # noqa: E402


def build_skin(image: np.ndarray, lab: np.ndarray, landmarks: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """analyze_image_detail과 같은 함수로 피부 마스크를 만든다 (로직 중복 방지)."""
    regions, coverage = sa._build_skin_regions(image, lab, landmarks)
    skin = np.zeros(image.shape[:2], dtype=np.uint8)
    for mask in regions.values():
        skin = cv2.bitwise_or(skin, mask)
    # 부위별 피부 노출 비율 출력 (가려져서 제외된 부위 확인용)
    for name, ratio in coverage.items():
        state = "사용" if name in regions else "제외(가려짐)"
        print(f"  {name:12s} 피부 노출 {ratio * 100:5.1f}%  → {state}")
    return skin, list(regions)


def trouble_detail(index_map: np.ndarray, skin: np.ndarray, face_width: float) -> dict:
    """sa._trouble과 같은 계산을 하되, 중간 결과(마스크·임계값)를 모두 돌려준다."""
    # 센서 노이즈 완화
    smooth = cv2.GaussianBlur(index_map.astype(np.float32), (3, 3), 0)

    # 피부 중앙값 기준으로 uint8 격자에 담기 (±8 지수 밖은 잘림)
    center = float(np.median(smooth[skin > 0]))
    fine = (smooth - center) * sa.TROUBLE_INDEX_GAIN
    scaled = np.clip(fine + 128.0, 0, 255).astype(np.uint8)
    clipped_low = float(np.mean(fine[skin == 0] < -128))  # 피부 밖에서 하한에 잘린 비율

    # 주변(국소) 중앙값 대비 편차
    kernel = max(3, int(face_width * 0.05) | 1)
    local_median = cv2.medianBlur(scaled, kernel).astype(np.float32) - 128.0
    deviation = fine - local_median

    # 사진별 임계값
    spread = 1.4826 * float(np.median(np.abs(deviation[skin > 0])))
    threshold = max(sa.TROUBLE_MIN_THRESHOLD * sa.TROUBLE_INDEX_GAIN, sa.TROUBLE_SIGMA_FACTOR * spread)
    candidate = ((deviation > threshold) & (skin > 0)).astype(np.uint8)

    # 덩어리 크기 필터
    min_diameter = max(2.0, face_width * sa.TROUBLE_MIN_BLOB_RATIO)
    min_area = max(4, int(np.pi / 4 * min_diameter**2))
    # 피부 영역 가장자리 띠 (sa._trouble과 같은 기준)
    band_px = max(2, int(round(face_width * sa.TROUBLE_EDGE_BAND_RATIO)))
    edge_band = sa._outer_edge_band(skin, band_px)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    kept_ids, edge_ids = [], []
    for i in range(1, count):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue  # 크기 미달 → 노이즈
        if np.count_nonzero(edge_band & (labels == i)) / area >= sa.TROUBLE_MAX_EDGE_SHARE:
            edge_ids.append(i)  # 가장자리 경계 효과 → 제외
            continue
        kept_ids.append(i)
    kept = np.isin(labels, kept_ids).astype(np.uint8)
    edge_dropped = np.isin(labels, edge_ids).astype(np.uint8)

    skin_px = int(np.count_nonzero(skin))
    return {
        "candidate": candidate,
        "kept": kept,
        "edge_dropped": edge_dropped,
        "kernel": kernel,
        "spread": spread / sa.TROUBLE_INDEX_GAIN,        # 지수 단위로 환산
        "threshold": threshold / sa.TROUBLE_INDEX_GAIN,
        "threshold_is_floor": threshold == sa.TROUBLE_MIN_THRESHOLD * sa.TROUBLE_INDEX_GAIN,
        "min_area": min_area,
        "blob_count": len(kept_ids),
        "edge_blob_count": len(edge_ids),
        "blob_areas": sorted((int(stats[i, cv2.CC_STAT_AREA]) for i in kept_ids), reverse=True),
        "candidate_ratio": int(candidate.sum()) / skin_px,
        "ratio": int(kept.sum()) / skin_px,
        "clipped_low": clipped_low,
    }


def edge_share(kept: np.ndarray, skin: np.ndarray, width: int) -> float:
    """트러블 픽셀 중 피부 영역 경계에서 width px 이내에 있는 비율.

    높으면 '진짜 반점'보다 패치 가장자리(머리카락·그늘·배경 경계) 효과일 가능성이 크다.
    """
    if kept.sum() == 0:
        return 0.0
    inner = cv2.erode(skin, np.ones((3, 3), np.uint8), iterations=width)
    edge = (skin > 0) & (inner == 0)
    return float(np.count_nonzero(edge & (kept > 0)) / np.count_nonzero(kept))


def main() -> None:
    parser = argparse.ArgumentParser(description="트러블 점수 진단")
    parser.add_argument("photo", type=Path, help="얼굴 사진 경로")
    parser.add_argument("--out", type=Path, help="오버레이 저장 경로 (기본: <사진>_trouble.png)")
    args = parser.parse_args()

    # 1) 실제 분석과 동일한 전처리
    image = sa._decode(args.photo.read_bytes())
    landmarks = sa._detect_landmarks(image)
    balanced = sa._white_balance(image)
    lab = cv2.cvtColor(balanced, cv2.COLOR_BGR2LAB)
    face_width = float(np.ptp(landmarks[:, 0]))
    skin, used = build_skin(image, lab, landmarks)
    index_map = sa._redness_index(balanced)

    # 2) 트러블 계산 (중간값 포함)
    d = trouble_detail(index_map, skin, face_width)
    score_official, ratio_official, _ = sa._trouble(index_map, skin, face_width)
    score = sa._linear_score(d["ratio"], *sa.TROUBLE_RANGE)

    # 3) 수치 출력
    lo, hi = sa.TROUBLE_RANGE
    print(f"이미지 크기        : {image.shape[1]}x{image.shape[0]} (축소 후)")
    print(f"얼굴 너비          : {face_width:.0f}px   사용 부위: {', '.join(used)}")
    print(f"피부 픽셀          : {int(np.count_nonzero(skin))}")
    print(f"국소 중앙값 커널   : {d['kernel']}px")
    print(f"질감 변동폭(spread): {d['spread']:.3f}  → 임계값 {d['threshold']:.3f}"
          f"{'  (하한값 적용)' if d['threshold_is_floor'] else ''}")
    print(f"임계값 초과 비율   : {d['candidate_ratio'] * 100:.2f}%  (크기 필터 전)")
    print(f"최소 덩어리 면적   : {d['min_area']}px")
    print(f"트러블 덩어리      : {d['blob_count']}개, 상위 면적 {d['blob_areas'][:10]}")
    print(f"가장자리 제외      : {d['edge_blob_count']}개  (패치 경계에 걸친 가짜 덩어리)")
    print(f"트러블 면적 비율   : {d['ratio'] * 100:.2f}%  (100점 기준 {hi * 100:.1f}%)")
    print(f"트러블 점수        : {score}  (실제 로직: {score_official}, 일치: {score == score_official})")
    print(f"경계 3px 이내 비율 : {edge_share(d['kept'], skin, 3) * 100:.0f}%  (높으면 패치 가장자리 효과 의심)")
    print(f"피부 밖 하한 잘림  : {d['clipped_low'] * 100:.1f}%  (배경이 피부보다 훨씬 덜 붉은 정도)")

    # 4) 오버레이 이미지 저장
    overlay = image.copy()
    overlay[(d["candidate"] > 0) & (d["kept"] == 0) & (d["edge_dropped"] == 0)] = (0, 255, 255)  # 노랑: 버려진 노이즈
    overlay[d["edge_dropped"] > 0] = (255, 0, 255)                     # 보라: 가장자리라 제외
    overlay[d["kept"] > 0] = (0, 0, 255)                               # 빨강: 트러블
    contours, _ = cv2.findContours(skin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 1)            # 초록: 피부 영역
    out = args.out or args.photo.with_name(f"{args.photo.stem}_trouble.png")
    cv2.imwrite(str(out), np.hstack([image, overlay]))
    print(f"\n오버레이 저장      : {out}")


if __name__ == "__main__":
    main()
