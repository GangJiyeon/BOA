"""합성 트러블 주입 검증: 크기와 붉은 정도를 아는 점을 사진에 넣고, 트러블 탐지가 잡아내는지 본다.

사람이 필요 없는 검증이다. 정답(점의 위치·크기)을 알고 있으므로
"지름 몇 mm, 얼마나 붉은 점부터 잡아내는가"를 수치로 말할 수 있다.

방법
  1) 깨끗한 사진을 먼저 분석해 기준 트러블 픽셀 수를 구한다.
  2) 볼·볼 아래쪽의 정해진 위치에 붉은 점을 '한 개씩' 넣고 다시 분석한다.
     (점은 원본 해상도에 그리고 JPEG로 다시 저장하므로, 실제 촬영과 같은 경로를 거친다)
  3) 늘어난 트러블 픽셀이 점 면적의 절반 이상이면 '검출'로 본다.

점의 붉은 정도(대비)는 분석 코드의 홍조 지수 단위로 준다.
  대비 3 = 주변 피부보다 홍조 지수가 3 높은 점 (분석 코드의 트러블 임계값은 0.8)
점 지름은 얼굴 너비를 FACE_WIDTH_MM(기본 140mm)로 가정해 mm로 환산한다.

사진은 저장하지 않는다. 결과는 output/synthetic_trouble.csv에 수치로만 남는다.

사용법 (backend 폴더에서)
    .venv\\Scripts\\python scripts/validation/synthetic_trouble.py 사진폴더
    .venv\\Scripts\\python scripts/validation/synthetic_trouble.py 사진폴더 --sizes 1 2 3 4 --contrasts 2 4
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

import _common as c

sa = c.sa

# 얼굴 너비 가정값 (mm). 랜드마크 좌우 폭은 성인 기준 약 13~15cm다.
FACE_WIDTH_MM = 140.0

# 점을 넣을 위치: (기준 랜드마크 번호, 오른쪽 이동, 아래쪽 이동) — 이동량은 얼굴 너비 대비
# 분석 코드의 트러블 영역(볼 반지름 0.13, 볼 아래 0.09) 안쪽에 들어가도록 잡았다.
POSITIONS = [
    (50, 0.0, 0.0),     # 왼볼 중심
    (50, -0.03, 0.03),  # 왼볼 바깥 아래
    (280, 0.0, 0.0),    # 오른볼 중심
    (280, 0.03, 0.03),  # 오른볼 바깥 아래
    (187, 0.0, 0.0),    # 왼볼 아래쪽
    (411, 0.0, 0.0),    # 오른볼 아래쪽
]

DEFAULT_SIZES_MM = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
DEFAULT_CONTRASTS = [1.5, 3.0, 6.0]

# 점 면적 중 이 비율 이상이 트러블로 늘어나면 '검출'
DETECT_FRACTION = 0.5
# 점 면적 중 이 비율 이상이 트러블 분석 영역 안에 있어야 시험한다 (머리카락 등에 걸치면 제외)
MIN_INSIDE_FRACTION = 0.9

DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "synthetic_trouble.csv"


# ── 점 그리기 ────────────────────────────────────────────────────────


def disk_alpha(shape: tuple[int, int], cx: float, cy: float, radius: float) -> tuple[slice, slice, np.ndarray]:
    """가장자리를 1픽셀 부드럽게 처리한 원형 마스크(0~1)를 점 주변 창 단위로 만든다."""
    h, w = shape
    pad = int(np.ceil(radius)) + 2
    y0, y1 = max(0, int(cy) - pad), min(h, int(cy) + pad + 1)
    x0, x1 = max(0, int(cx) - pad), min(w, int(cx) + pad + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    alpha = np.clip(radius + 0.5 - dist, 0.0, 1.0)
    return slice(y0, y1), slice(x0, x1), alpha


def inject_dot(image: np.ndarray, cx: float, cy: float, diameter: float, contrast: float) -> np.ndarray:
    """홍조 지수(100*log10(R/G))가 contrast만큼 높아지도록 G·B 채널을 낮춘 점을 그린다."""
    out = image.astype(np.float32).copy()
    ys, xs, alpha = disk_alpha(image.shape[:2], cx, cy, diameter / 2)
    factor = 10 ** (-contrast / 100.0)          # G를 이만큼 곱하면 지수가 contrast 오른다
    gain = 1.0 - alpha * (1.0 - factor)         # 점 안쪽은 factor, 바깥은 1
    out[ys, xs, 0] *= gain                      # B (자연스러운 색을 위해 G와 같이 낮춤)
    out[ys, xs, 1] *= gain                      # G
    return np.clip(out, 0, 255).astype(np.uint8)


def encode_jpeg(image: np.ndarray) -> bytes:
    """실제 업로드와 같은 경로를 타도록 JPEG(품질 95)로 다시 저장한다."""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise RuntimeError("JPEG 인코딩 실패")
    return buf.tobytes()


# ── 사진 한 장 시험 ──────────────────────────────────────────────────


def test_photo(path: Path, args: argparse.Namespace) -> list[dict]:
    """사진 한 장에 대해 (위치 × 크기 × 대비) 조합을 하나씩 시험한다."""
    data = path.read_bytes()

    # 1) 기준 분석 (점을 넣기 전)
    base_raw, error = c.analyze_bytes(data, args.profile, args.min_face_width)
    if error:
        print(f"  거절  {path.name}  ({error}) — 이 사진은 건너뜀")
        return []
    base_px = base_raw["blemish_ratio"] * base_raw["trouble_skin_px"]

    # 2) 원본 좌표의 랜드마크 (점을 원본 해상도에 그리기 위해)
    full = sa._decode_full(data)
    preview, scale = sa._shrink(full)
    lm_full = sa._detect_landmarks(preview) / scale
    fw_full = float(np.ptp(lm_full[:, 0]))

    # 3) 분석 해상도의 트러블 영역 (점이 분석 영역 안에 들어가는지 확인용)
    profile = sa.get_camera_profile(args.profile)
    face = sa._prepare_face(data, min_face_width=args.min_face_width, channel_gains=profile.channel_gains)
    area = sa._trouble_area(face.image, face.lab, face.landmarks) > 0
    fw_an = face.face_width

    print(f"  시험  {path.name}  (기준 트러블 비율 {base_raw['blemish_ratio']:.4f}, 분석 얼굴 너비 {fw_an:.0f}px)")

    rows: list[dict] = []
    for idx, dx, dy in POSITIONS:
        for size_mm in args.sizes:
            d_ratio = size_mm / args.face_mm                 # 얼굴 너비 대비 지름
            d_an = d_ratio * fw_an                           # 분석 해상도에서의 지름(px)
            expected_px = np.pi / 4 * d_an**2

            # 분석 해상도에서 점이 트러블 영역 안에 충분히 들어가는지 확인
            ax = face.landmarks[idx, 0] + dx * fw_an
            ay = face.landmarks[idx, 1] + dy * fw_an
            ys, xs, alpha = disk_alpha(area.shape, ax, ay, max(d_an / 2, 0.5))
            inside = float((alpha * area[ys, xs]).sum() / max(alpha.sum(), 1e-6))
            if inside < MIN_INSIDE_FRACTION:
                for contrast in args.contrasts:
                    rows.append({"file": path.name, "landmark": idx, "dx": dx, "dy": dy,
                                 "size_mm": size_mm, "contrast": contrast, "status": "영역 밖"})
                continue

            # 원본 해상도에 점을 그린다
            cx = lm_full[idx, 0] + dx * fw_full
            cy = lm_full[idx, 1] + dy * fw_full
            for contrast in args.contrasts:
                dotted = inject_dot(full, cx, cy, d_ratio * fw_full, contrast)
                raw, err = c.analyze_bytes(encode_jpeg(dotted), args.profile, args.min_face_width)
                row = {"file": path.name, "landmark": idx, "dx": dx, "dy": dy,
                       "size_mm": size_mm, "contrast": contrast, "expected_px": round(expected_px, 1)}
                if err:
                    row["status"] = f"거절({err})"
                else:
                    gained = raw["blemish_ratio"] * raw["trouble_skin_px"] - base_px
                    row["gained_px"] = round(gained, 1)
                    row["recovered"] = round(gained / expected_px, 3) if expected_px else 0.0
                    row["status"] = "검출" if gained >= DETECT_FRACTION * expected_px else "놓침"
                rows.append(row)
    return rows


# ── 보고 ────────────────────────────────────────────────────────────


def report(rows: list[dict], sizes: list[float], contrasts: list[float], face_mm: float) -> None:
    """크기 × 대비별 검출률 표와, 대비별 최소 검출 크기를 출력한다."""
    tested = [r for r in rows if r["status"] in ("검출", "놓침")]
    if not tested:
        print("\n시험된 조합이 없습니다.")
        return

    cell: dict[tuple[float, float], list[dict]] = defaultdict(list)
    for r in tested:
        cell[(float(r["size_mm"]), float(r["contrast"]))].append(r)

    print("\n" + "=" * 66)
    print("1. 검출률 (%)  — 행: 점 지름(mm), 열: 대비(홍조 지수)")
    print("=" * 66)
    print(f"  {'지름':>6}" + "".join(f"{'대비 ' + format(ct, 'g'):>12}" for ct in contrasts))
    for size in sizes:
        cells = []
        for ct in contrasts:
            group = cell.get((size, ct), [])
            if group:
                rate = sum(r["status"] == "검출" for r in group) / len(group) * 100
                cells.append(f"{rate:.0f}% (n={len(group)})".rjust(12))
            else:
                cells.append(f"{'-':>12}")
        print(f"  {format(size, 'g') + 'mm':>6}" + "".join(cells))

    print("\n" + "=" * 66)
    print("2. 최소 검출 크기 — 검출률 90% 이상이 되는 가장 작은 지름")
    print("=" * 66)
    for ct in contrasts:
        found = None
        for size in sizes:
            group = cell.get((size, ct), [])
            if group and sum(r["status"] == "검출" for r in group) / len(group) >= 0.9:
                found = size
                break
        print(f"  대비 {ct:g}: {f'{found:g}mm' if found else '시험 범위 안에서 90% 미달'}")

    print("\n" + "=" * 66)
    print("3. 면적 회수율 — 점 면적 대비 늘어난 트러블 픽셀 (1.0이면 점 크기 그대로 잡음)")
    print("=" * 66)
    print(f"  {'지름':>6}" + "".join(f"{'대비 ' + format(ct, 'g'):>12}" for ct in contrasts))
    for size in sizes:
        cells = []
        for ct in contrasts:
            group = cell.get((size, ct), [])
            cells.append(f"{c.mean([float(r['recovered']) for r in group]):12.2f}" if group else f"{'-':>12}")
        print(f"  {format(size, 'g') + 'mm':>6}" + "".join(cells))

    skipped = [r for r in rows if r["status"] not in ("검출", "놓침")]
    if skipped:
        kinds = defaultdict(int)
        for r in skipped:
            kinds[r["status"]] += 1
        print("\n  제외된 조합: " + ", ".join(f"{k} {v}건" for k, v in kinds.items()))
    print(f"\n  가정: 얼굴 너비 {face_mm:g}mm 기준으로 지름을 환산했다 (--face-mm로 변경).")


def main() -> None:
    parser = argparse.ArgumentParser(description="합성 트러블 주입 검증")
    parser.add_argument("folder", type=Path, help="트러블이 적은 깨끗한 정면 사진 폴더")
    parser.add_argument("--sizes", type=float, nargs="+", default=DEFAULT_SIZES_MM, help="점 지름(mm) 목록")
    parser.add_argument("--contrasts", type=float, nargs="+", default=DEFAULT_CONTRASTS, help="대비(홍조 지수) 목록")
    parser.add_argument("--face-mm", type=float, default=FACE_WIDTH_MM, help="얼굴 너비 가정값(mm)")
    parser.add_argument("--profile", default=c.default_profile(), help="카메라 프로필 (기본: .env 값)")
    parser.add_argument("--min-face-width", type=int, default=c.default_min_face_width())
    parser.add_argument("--limit", type=int, default=0, help="사진 수 제한 (0이면 전부)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if not args.folder.is_dir():
        sys.exit(f"폴더가 없습니다: {args.folder}")
    photos = c.list_images(args.folder)
    if args.limit:
        photos = photos[: args.limit]
    if not photos:
        sys.exit(f"사진이 없습니다: {args.folder}")

    total = len(photos) * len(POSITIONS) * len(args.sizes) * len(args.contrasts)
    print(f"합성 트러블 검증 — 사진 {len(photos)}장, 최대 {total}회 분석 (카메라 프로필: {args.profile})\n")

    rows: list[dict] = []
    for path in photos:
        rows.extend(test_photo(path, args))

    if rows:
        c.save_csv(rows, args.out)
    report(rows, args.sizes, args.contrasts, args.face_mm)


if __name__ == "__main__":
    main()
