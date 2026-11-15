"""카메라 프로필 재보정 도우미: 새 장소·기기에서 찍은 사진으로 권장 값을 계산한다.

시연 장소가 바뀌면 그 장소에서 사진을 찍고 이 스크립트를 돌린 뒤,
출력된 권장 값을 app/services/skin_analysis.py의 CAMERA_PROFILES와
app/services/skin_tone.py의 TONE_THRESHOLDS에 옮겨 적는다.

계산하는 것
  1) 사진별 원시값: 홍조 지수, 균일도 편차(이마·양볼), 피부톤(ITA°·색상각), 얼굴 너비, 양볼 밝기 비율
  2) 균일도 권장 범위: 휴대폰 기준 범위를 '깨끗한 피부 중앙값' 비율만큼 옮긴다
     (갤럭시북 프로필을 만든 방식과 같다. "표본이 휴대폰 표본과 비슷한 피부"라는 가정이 들어간다)
  3) 홍조: 표본이 현재 프로필 범위 안에 들어오는지 확인
  4) 피부톤: --labels로 정답(웜/뉴트럴/쿨)을 주면 판정 일치 여부를 표시

사용법 (backend 폴더에서)
    .venv\\Scripts\\python scripts/validation/calibrate_profile.py 사진폴더 --profile galaxybook
    .venv\\Scripts\\python scripts/validation/calibrate_profile.py 사진폴더 --labels 정답.csv

정답 CSV 형식 (선택): file,undertone   예) 샘플1.jpg,cool
사진은 저장하지 않는다. 결과는 output/calibrate_profile.csv에 수치로만 남는다.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

import _common as c

sa = c.sa
from app.services import skin_tone  # noqa: E402  (_common이 import 경로를 잡아준 뒤)

# 휴대폰 기준값 (skin_analysis.UNIFORMITY_STD_RANGE를 정한 표본)
# 같은위치사진 5장의 이마·양볼 균일도 편차 중앙값
PHONE_CLEAN_MEDIAN_STD = 2.16
DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "calibrate_profile.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="카메라 프로필 재보정 도우미")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", default=c.default_profile(), help="비교할 현재 프로필 (기본: .env 값)")
    parser.add_argument("--min-face-width", type=int, default=c.default_min_face_width())
    parser.add_argument("--labels", type=Path, help="정답 CSV (file,undertone)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    photos = c.list_images(args.folder)
    if not photos:
        sys.exit(f"사진이 없습니다: {args.folder}")
    labels = {}
    if args.labels:
        with open(args.labels, encoding="utf-8-sig") as fh:
            labels = {r["file"]: r["undertone"].strip().lower() for r in csv.DictReader(fh)}

    profile = sa.get_camera_profile(args.profile)
    rows = []
    print(f"프로필: {args.profile}  (홍조 범위 {profile.redness_range}, 균일도 범위 {profile.uniformity_std_range})\n")
    print(f"  {'사진':<14}{'얼굴px':>7}{'양볼비':>7}{'홍조지수':>9}{'홍조':>5}{'균일편차':>9}{'균일도':>7}"
          f"{'ITA°':>7}{'h°':>7}  톤 판정")
    for path in photos:
        data = path.read_bytes()
        try:
            scores, raw = sa.analyze_image_detail(data, min_face_width=args.min_face_width, camera_profile=args.profile)
            tone = skin_tone.measure_tone(data, min_face_width=args.min_face_width, camera_profile=args.profile)
        except sa.AnalysisError as e:
            print(f"  {path.name:<14} 거절 ({e.code})")
            continue
        verdict = f"{skin_tone.BRIGHTNESS_LABELS[tone.brightness_level]} {skin_tone.UNDERTONE_LABELS[tone.undertone]}"
        mark = ""
        if path.name in labels:
            mark = "  ✓ 정답 일치" if labels[path.name] == tone.undertone else f"  ✗ 정답 {labels[path.name]}"
        print(f"  {path.stem[:13]:<14}{raw['source_face_width_px']:>7.0f}{raw.get('cheek_l_ratio', float('nan')):>7.3f}"
              f"{raw['redness_index']:>9.2f}{scores['redness']:>5}{raw['std_l_skin']:>9.2f}{scores['uniformity']:>7}"
              f"{tone.raw['ita_deg']:>7.1f}{tone.raw['hue_deg']:>7.1f}  {verdict}{mark}")
        rows.append({"file": path.name, "face_px": raw["source_face_width_px"], "cheek_ratio": raw.get("cheek_l_ratio"),
                     "redness_index": raw["redness_index"], "uniformity_std": raw["std_l_skin"],
                     "ita": tone.raw["ita_deg"], "hue": tone.raw["hue_deg"], "tone": f"{tone.brightness_level}/{tone.undertone}",
                     "label": labels.get(path.name, "")})

    if not rows:
        sys.exit("분석된 사진이 없습니다.")

    med = lambda k: statistics.median(r[k] for r in rows)  # noqa: E731
    lo, hi = min(r["redness_index"] for r in rows), max(r["redness_index"] for r in rows)
    print("\n── 권장 값 ──────────────────────────────────────────────")
    # 균일도
    scale = med("uniformity_std") / PHONE_CLEAN_MEDIAN_STD
    base_lo, base_hi = sa.UNIFORMITY_STD_RANGE
    print(f"균일도 편차 중앙값 {med('uniformity_std'):.2f} (휴대폰 {PHONE_CLEAN_MEDIAN_STD}) → 배율 {scale:.2f}")
    print(f"  권장 uniformity_std_range = ({base_lo * scale:.2f}, {base_hi * scale:.2f})"
          f"   현재 {profile.uniformity_std_range}")
    # 홍조
    r_lo, r_hi = profile.redness_range
    below = sum(r["redness_index"] < r_lo for r in rows)
    above = sum(r["redness_index"] > r_hi for r in rows)
    verdict = "중앙값이 범위 안 (유지 가능)" if r_lo <= med("redness_index") <= r_hi else "중앙값이 범위 밖 (재설정 필요)"
    print(f"홍조 지수 {lo:.2f}~{hi:.2f}, 중앙값 {med('redness_index'):.2f} → 현재 범위 {profile.redness_range}: {verdict}"
          f"  (하한 미만 {below}장 = 0점, 상한 초과 {above}장 = 100점)")
    # 피부톤
    print(f"피부톤 중앙값 ITA° {med('ita'):.1f}, 색상각 {med('hue'):.1f}° "
          f"(색상각 범위 {min(r['hue'] for r in rows):.1f}~{max(r['hue'] for r in rows):.1f}°)")
    if labels:
        hit = [r for r in rows if r["label"]]
        ok = sum(r["tone"].split("/")[1] == r["label"] for r in hit)
        print(f"  언더톤 정답 일치 {ok}/{len(hit)}명")
    else:
        print("  언더톤 경계는 정답이 있어야 정할 수 있다 (--labels 사용)")
    # 촬영 조건 경고
    small = [r["file"] for r in rows if r["face_px"] < sa.ANALYSIS_FACE_WIDTH * 0.85]
    if small:
        print(f"주의: 얼굴이 작게 찍힌 사진 {len(small)}장 (설계 기준 {sa.ANALYSIS_FACE_WIDTH}px). 더 가까이 앉아 찍으면 트러블 검출이 좋아진다.")

    c.save_csv(rows, args.out)


if __name__ == "__main__":
    main()
