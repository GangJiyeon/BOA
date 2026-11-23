"""피부톤(쿠션 호수) 현장 보정: 정답 호수를 아는 사람 사진으로 카메라 보정값을 계산한다.

계산하는 값 (app/services/skin_tone.py 의 보정 ITA 방식)
    보정 ITA° = arctan((L* + l_offset - 50) / (b* × b_scale))  →  ITA-호수 대응표  →  추정 호수
    - l_offset: 카메라가 피부를 어둡게/밝게 기록하는 정도
    - b_scale : 카메라가 노란 기를 바래게 기록하는 정도
    정답 호수와 추정 호수의 차이가 가장 작아지는 l_offset·b_scale을 찾는다.

정답 인원수에 따른 동작
    1명   : l_offset은 지금 값으로 두고 b_scale만 맞춘다 (미지수 2개를 1명으로는 정할 수 없음)
    2명+  : 둘 다 맞춘다. 지금 값에서 너무 멀리 가지 않도록 약하게 붙잡는다.
    3명+  : 한 명씩 빼고 맞춘 뒤 뺀 사람을 맞히는 '교차 검증 오차'도 출력한다 (실제 정확도에 가까움).

사용법 (backend 폴더에서)
    # 1) 정답 CSV 작성 (file,shade)   예) 샘플3.jpg,23
    # 2) 결과만 보기 (파일은 안 바뀜)
    .venv\\Scripts\\python scripts/calibrate_tone.py 정답.csv --photos photos --profile galaxybook
    # 3) 마음에 들면 --write 로 app/data/tone_calibration.json 에 저장 → 서버가 다음 요청부터 자동 반영
    .venv\\Scripts\\python scripts/calibrate_tone.py 정답.csv --photos photos --profile galaxybook --write
    # Docker 안에서 실행할 때
    docker compose exec api python scripts/calibrate_tone.py 정답.csv --photos photos --profile galaxybook --write

사진은 저장하지 않는다. 보정 파일에는 숫자와 파일 이름만 남는다.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# backend 폴더를 import 경로에 넣는다
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import skin_analysis as sa  # noqa: E402
from app.services import skin_tone as st  # noqa: E402

# ── 탐색 범위 ──
OFFSET_GRID = np.arange(-10.0, 25.0001, 0.05)   # l_offset 후보
SCALE_GRID = np.arange(0.5, 3.0001, 0.002)      # b_scale 후보
# 지금 값에서 멀어질수록 주는 벌점 (정답이 적을 때 엉뚱한 값으로 튀는 것을 막음)
# 오프셋 5, 배율 0.5 만큼 벗어나면 호수 오차 약 0.3호(제곱 0.1)에 해당
PULL_OFFSET, PULL_SCALE = 0.1 / 5.0**2, 0.1 / 0.5**2


def _env_value(key: str) -> str | None:
    """환경변수 → backend/.env 순서로 값 하나를 읽는다 (다른 값은 읽지 않는다)."""
    if os.environ.get(key):
        return os.environ[key]
    env = BACKEND_DIR / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


# ── 대응표 계산 (numpy 벡터 버전: 격자 탐색을 빠르게) ──
_ITA_ASC = sorted(st.ITA_SHADE, key=lambda p: p[1])
_ITA_X = np.array([i for _, i in _ITA_ASC])
_ITA_Y = np.array([float(s) for s, _ in _ITA_ASC])


def shade_vec(L: np.ndarray, b: np.ndarray, off: np.ndarray, scale: np.ndarray) -> np.ndarray:
    """보정 ITA → 호수 (skin_tone.shade_from_ita와 같은 계산, 배열 입력)."""
    ita = np.degrees(np.arctan((L + off - 50.0) / (b * scale)))
    y = np.interp(ita, _ITA_X, _ITA_Y)
    lo_slope = (_ITA_Y[1] - _ITA_Y[0]) / (_ITA_X[1] - _ITA_X[0])
    hi_slope = (_ITA_Y[-1] - _ITA_Y[-2]) / (_ITA_X[-1] - _ITA_X[-2])
    y = np.where(ita < _ITA_X[0], _ITA_Y[0] + (ita - _ITA_X[0]) * lo_slope, y)
    y = np.where(ita > _ITA_X[-1], _ITA_Y[-1] + (ita - _ITA_X[-1]) * hi_slope, y)
    return np.clip(y, st.SHADE_MIN, st.SHADE_MAX)


def fit(samples: list[dict], off0: float, scale0: float, *, fix_offset: bool) -> tuple[float, float]:
    """정답 호수와의 제곱 오차 + 벌점이 가장 작은 (l_offset, b_scale)."""
    L = np.array([s["L"] for s in samples])[:, None, None]
    b = np.array([s["b"] for s in samples])[:, None, None]
    true = np.array([s["shade"] for s in samples])[:, None, None]
    offs = np.array([off0]) if fix_offset else OFFSET_GRID
    off, scale = np.meshgrid(offs, SCALE_GRID, indexing="ij")
    err = ((shade_vec(L, b, off[None], scale[None]) - true) ** 2).mean(axis=0)
    err = err + PULL_OFFSET * (off - off0) ** 2 + PULL_SCALE * (scale - scale0) ** 2
    i, j = np.unravel_index(np.argmin(err), err.shape)
    return float(off[i, j]), float(scale[i, j])


def predict(s: dict, off: float, scale: float) -> float:
    return float(shade_vec(np.array(s["L"]), np.array(s["b"]), np.array(off), np.array(scale)))


def nearest_step(shade: float) -> int:
    return min(st.SHADE_STEPS, key=lambda v: abs(v - shade))


def summary(samples: list[dict], key: str) -> str:
    errs = [abs(s[key] - s["shade"]) for s in samples]
    hit = sum(abs(nearest_step(s[key]) - s["shade"]) <= 2 for s in samples)
    return f"평균 오차 {np.mean(errs):.2f}호 · 최대 {max(errs):.2f}호 · 안내 범위(±2호) 적중 {hit}/{len(samples)}"


def main() -> None:
    ap = argparse.ArgumentParser(description="피부톤 쿠션 호수 현장 보정")
    ap.add_argument("labels", type=Path, help="정답 CSV (열: file,shade)")
    ap.add_argument("--photos", type=Path, default=BACKEND_DIR / "photos", help="사진 폴더")
    ap.add_argument("--profile", default=_env_value("SKIN_CAMERA_PROFILE") or "phone")
    ap.add_argument("--min-face-width", type=int,
                    default=int(_env_value("MIN_FACE_WIDTH_PX") or sa.DEFAULT_MIN_FACE_WIDTH))
    ap.add_argument("--fix-offset", action="store_true", help="l_offset은 그대로 두고 b_scale만 맞춤")
    ap.add_argument("--write", action="store_true", help=f"결과를 {st.CALIBRATION_PATH.name} 에 저장")
    args = ap.parse_args()
    profile = args.profile.strip().lower()

    # 1) 정답 읽기
    with open(args.labels, encoding="utf-8-sig") as fh:
        rows = [(r["file"].strip(), float(r["shade"])) for r in csv.DictReader(fh) if r.get("file")]
    if not rows:
        sys.exit("정답 CSV가 비어 있습니다 (열 이름: file,shade)")

    # 2) 사진 측정 (보정 전 L*·b*)
    samples = []
    for name, shade in rows:
        path = args.photos / name
        try:
            t = st.measure_tone(path.read_bytes(), camera_profile=profile, min_face_width=args.min_face_width)
        except (OSError, sa.AnalysisError) as e:
            print(f"  건너뜀 {name}: {e}")
            continue
        samples.append({"file": name, "shade": shade, "L": t.raw["L"], "b": t.raw["b"]})
    if not samples:
        sys.exit("측정에 성공한 사진이 없습니다")

    # 3) 맞추기
    th = st.thresholds_for(profile)
    off0, scale0 = th.l_offset, th.b_scale
    fix = args.fix_offset or len(samples) == 1
    off, scale = fit(samples, off0, scale0, fix_offset=fix)
    for s in samples:
        s["before"] = predict(s, off0, scale0)
        s["after"] = predict(s, off, scale)

    # 4) 교차 검증 (3명 이상): 한 명씩 빼고 맞춘 값으로 뺀 사람을 예측
    if len(samples) >= 3:
        for k, s in enumerate(samples):
            o, sc = fit(samples[:k] + samples[k + 1:], off0, scale0, fix_offset=args.fix_offset)
            s["loo"] = predict(s, o, sc)

    # 5) 결과 출력
    print(f"\n프로필 {profile}  |  정답 {len(samples)}명  |  "
          f"{'b_scale만 맞춤' if fix else 'l_offset·b_scale 모두 맞춤'}")
    print(f"  지금 값 : l_offset {off0:+.2f}, b_scale {scale0:.3f}")
    print(f"  새 값   : l_offset {off:+.2f}, b_scale {scale:.3f}\n")
    print(f"  {'사진':16s} {'정답':>5s} {'L*':>6s} {'b*':>6s} {'지금':>6s} {'보정후':>6s}" + ("  교차검증" if "loo" in samples[0] else ""))
    for s in samples:
        line = f"  {s['file']:16s} {s['shade']:5.0f} {s['L']:6.2f} {s['b']:6.2f} {s['before']:6.1f} {s['after']:6.1f}"
        if "loo" in s:
            line += f"  {s['loo']:6.1f}"
        print(line)
    print(f"\n  지금   : {summary(samples, 'before')}")
    print(f"  보정후 : {summary(samples, 'after')}   ← 맞춘 사람으로 잰 값이라 실제보다 좋게 나옴")
    if "loo" in samples[0]:
        print(f"  교차검증: {summary(samples, 'loo')}   ← 새 사람에 대한 예상 정확도")
    elif len(samples) < 3:
        print("  ※ 정답이 3명 미만이라 정확도를 검증할 수 없습니다. 3명 이상을 권장합니다.")

    # 6) 저장
    if not args.write:
        print("\n저장하지 않았습니다. 적용하려면 --write 를 붙여 다시 실행하세요.")
        return
    path = st.CALIBRATION_PATH
    data = {}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("profiles", {})[profile] = {
        "l_offset": round(off, 3),
        "b_scale": round(scale, 4),
        # 아래는 기록용 (서버는 읽지 않음)
        "n": len(samples),
        "mae_fit": round(float(np.mean([abs(s["after"] - s["shade"]) for s in samples])), 3),
        "mae_cross_validation": (round(float(np.mean([abs(s["loo"] - s["shade"]) for s in samples])), 3)
                                 if "loo" in samples[0] else None),
        "files": [f"{s['file']}={s['shade']:g}" for s in samples],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n저장했습니다: {path}  (서버는 다음 분석 요청부터 이 값을 씁니다)")


if __name__ == "__main__":
    main()
