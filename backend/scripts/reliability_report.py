"""피부 분석 로직의 신뢰성 측정 스크립트.

사진 폴더를 디버그 엔드포인트에 차례로 올려 원시값을 모으고,
재현성·변별력·내적 일관성·지표 간 상관을 계산해 표로 출력한다.

사진 파일명 규칙
    {사람ID}_{회차}.jpg      예) A_1.jpg, A_2.jpg, A_3.jpg, B_1.jpg ...
    사람ID는 아무 문자열이나 쓸 수 있고, 회차는 1부터 센다.
    같은 사람을 같은 조건에서 여러 번 찍은 것이 재현성 측정의 전제다.

사용법
    python scripts/reliability_report.py photos/
    python scripts/reliability_report.py photos/ --url http://localhost:8000 --out result.csv

의존성은 httpx 하나뿐이며 이미 프로젝트에 포함되어 있다.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx

# 파일명에서 사람ID와 회차를 뽑는다
NAME_RE = re.compile(r"^(?P<subject>.+)_(?P<trial>\d+)$")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# 재현성·변별력을 계산할 원시 지표 (점수가 아니라 원시값을 쓴다.
# 점수는 구간에 눌린 값이라 미세한 변동이 보이지 않는다)
RAW_METRICS = [
    ("blemish_ratio", "트러블"),
    ("redness_index", "홍조"),
    ("mean_l_skin", "밝기"),
    ("std_l_skin", "균일도"),
]

# 홍조 내적 일관성 계산에 쓰는 부위별 지수
REDNESS_REGIONS = ["forehead_idx", "left_cheek_idx", "right_cheek_idx"]

# 촬영 조건이 실제로 고정됐는지 확인하는 보조 지표
CONDITION_KEYS = ["mean_l_skin", "face_width_px", "saturated_ratio", "skin_px"]


# ── 통계 ────────────────────────────────────────────────────────────


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def variance(xs: list[float], ddof: int = 1) -> float:
    """표본분산. 값이 하나뿐이면 0을 돌려준다."""
    n = len(xs)
    if n - ddof <= 0:
        return 0.0
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (n - ddof)


def pearson(xs: list[float], ys: list[float]) -> float:
    """두 변수의 선형 상관. 분산이 0이면 정의되지 않으므로 nan."""
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def icc1(groups: list[list[float]]) -> float | None:
    """급내상관계수 ICC(1,1).

    같은 사람을 여러 번 측정했을 때, 전체 변동 중 '사람 차이'가
    차지하는 비율. 1에 가까울수록 사람을 잘 구별한다는 뜻이고,
    0.75 이상을 양호, 0.9 이상을 우수로 본다.

    회차 수가 사람마다 달라도 되도록 균형 설계를 가정하지 않는다.
    """
    groups = [g for g in groups if len(g) >= 2]
    if len(groups) < 2:
        return None

    k_values = [len(g) for g in groups]
    k = mean(k_values)  # 평균 측정 횟수
    n = len(groups)
    all_values = [v for g in groups for v in g]
    grand = mean(all_values)

    # 사람 간 평균제곱: 각 사람 평균이 전체 평균에서 얼마나 떨어져 있나
    ss_between = sum(len(g) * (mean(g) - grand) ** 2 for g in groups)
    ms_between = ss_between / (n - 1)

    # 사람 내 평균제곱: 같은 사람의 측정값이 그 사람 평균에서 얼마나 흩어져 있나
    ss_within = sum((v - mean(g)) ** 2 for g in groups for v in g)
    df_within = sum(k_values) - n
    if df_within <= 0:
        return None
    ms_within = ss_within / df_within

    denom = ms_between + (k - 1) * ms_within
    if denom == 0:
        return None
    return (ms_between - ms_within) / denom


def cronbach_alpha(items: list[list[float]]) -> float | None:
    """내적 일관성 Cronbach alpha.

    items는 [항목][대상] 구조. 같은 것을 재는 여러 항목(여기서는
    이마·왼볼·오른볼의 홍조 지수)이 서로 맞물리는지 본다.
    0.7 이상이면 일관적이라고 본다.
    """
    k = len(items)
    if k < 2:
        return None
    n = len(items[0])
    if n < 2:
        return None

    item_var_sum = sum(variance(item) for item in items)
    totals = [sum(item[i] for item in items) for i in range(n)]
    total_var = variance(totals)
    if total_var == 0:
        return None
    return k / (k - 1) * (1 - item_var_sum / total_var)


# ── 수집 ────────────────────────────────────────────────────────────


def parse_name(path: Path) -> tuple[str, int] | None:
    m = NAME_RE.match(path.stem)
    if not m:
        return None
    return m.group("subject"), int(m.group("trial"))


def collect(folder: Path, base_url: str) -> list[dict]:
    """폴더의 사진을 하나씩 디버그 엔드포인트에 올려 결과를 모은다."""
    photos = sorted(
        p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not photos:
        sys.exit(f"사진이 없습니다: {folder}")

    rows: list[dict] = []
    rejected: list[tuple[str, str]] = []

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        for path in photos:
            parsed = parse_name(path)
            if parsed is None:
                print(f"  건너뜀 (파일명 규칙 불일치): {path.name}")
                continue
            subject, trial = parsed

            with path.open("rb") as fp:
                response = client.post(
                    "/api/skin/analyses/debug",
                    files={"file": (path.name, fp, "image/jpeg")},
                    data={"moisture_source": "none"},
                )

            if response.status_code != 201:
                detail = response.json().get("detail", {})
                code = detail.get("code", f"HTTP {response.status_code}")
                rejected.append((path.name, code))
                print(f"  거절  {path.name}  ({code})")
                continue

            payload = response.json()
            row = {"subject": subject, "trial": trial, "file": path.name}
            row.update(payload["raw"])
            # 판정 일치율 계산을 위해 지표별 카테고리도 남긴다
            for score in payload["scores"]:
                row[f"cat_{score['metric_code']}"] = score["category_name"]
                row[f"score_{score['metric_code']}"] = score["score"]
            rows.append(row)
            print(f"  수집  {path.name}  ({subject} {trial}회차)")

    print(f"\n수집 {len(rows)}장 / 거절 {len(rejected)}장")
    if photos:
        rate = len(rejected) / len(photos) * 100
        print(f"입력 거절률 {rate:.0f}%  (정상 사진이 거절되면 게이트가 과하다는 뜻)")
    return rows


# ── 보고 ────────────────────────────────────────────────────────────


def group_by_subject(rows: list[dict], key: str) -> list[list[float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if key in row:
            buckets[row["subject"]].append(float(row[key]))
    return list(buckets.values())


def report_condition(rows: list[dict]) -> None:
    """촬영 조건이 실제로 고정됐는지 먼저 확인한다.

    조명이 들쭉날쭉하면 아래 수치가 전부 무의미해지므로 가장 먼저 본다.
    """
    print("\n" + "=" * 62)
    print("0. 촬영 조건 점검")
    print("=" * 62)
    for key in CONDITION_KEYS:
        values = [float(r[key]) for r in rows if key in r]
        if not values:
            continue
        lo, hi = min(values), max(values)
        print(f"  {key:18} {lo:9.3f} ~ {hi:9.3f}")
    l_values = [float(r["mean_l_skin"]) for r in rows if "mean_l_skin" in r]
    if l_values and (max(l_values) - min(l_values)) > 25:
        print("\n  주의: 피부 밝기 편차가 25를 넘습니다. 조명이 고정되지 않았을")
        print("        가능성이 있고, 그러면 아래 재현성 수치가 과소평가됩니다.")


def report_repeatability(rows: list[dict]) -> None:
    """같은 사람을 여러 번 찍었을 때 결과가 얼마나 일정한가."""
    print("\n" + "=" * 62)
    print("1. 재현성 — 같은 사람, 같은 조건, 반복 측정")
    print("=" * 62)
    print(f"  {'지표':<8} {'사람내 변동계수':>14} {'판정 일치율':>12}")
    print("  " + "-" * 38)

    for key, label in RAW_METRICS:
        groups = [g for g in group_by_subject(rows, key) if len(g) >= 2]
        if not groups:
            print(f"  {label:<8} {'측정 불가 (반복 촬영 없음)':>30}")
            continue
        # 사람마다 변동계수를 구해 평균낸다
        cvs = []
        for g in groups:
            m = mean(g)
            if m != 0:
                cvs.append(math.sqrt(variance(g)) / abs(m) * 100)
        cv = mean(cvs) if cvs else float("nan")

        # 판정(카테고리) 일치율: 사람별로 모든 회차가 같은 판정인가
        code = {"트러블": "trouble", "홍조": "redness",
                "밝기": "brightness", "균일도": "uniformity"}[label]
        cats: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            name = row.get(f"cat_{code}")
            if name:
                cats[row["subject"]].add(name)
        multi = {s: v for s, v in cats.items() if len(v) >= 1}
        same = sum(1 for v in multi.values() if len(v) == 1)
        agree = same / len(multi) * 100 if multi else float("nan")

        print(f"  {label:<8} {cv:13.1f}% {agree:11.0f}%")

    print("\n  변동계수 10% 이하, 판정 일치율 90% 이상이면 양호하다.")


def report_discriminability(rows: list[dict]) -> None:
    """사람을 구별하는가. 사람 간 차이가 사람 내 흔들림보다 큰가."""
    print("\n" + "=" * 62)
    print("2. 변별력 — 급내상관계수 ICC(1,1)")
    print("=" * 62)
    print(f"  {'지표':<8} {'ICC':>8}  {'해석':<10} {'사람간 범위':>22}")
    print("  " + "-" * 54)

    for key, label in RAW_METRICS:
        groups = group_by_subject(rows, key)
        value = icc1(groups)
        subject_means = [mean(g) for g in groups if g]
        if subject_means:
            lo, hi = min(subject_means), max(subject_means)
            span = f"{lo:.4f} ~ {hi:.4f}"
        else:
            span = "-"

        if value is None:
            print(f"  {label:<8} {'측정 불가':>8}  {'반복 촬영 필요':<10} {span:>22}")
            continue
        if value >= 0.9:
            verdict = "우수"
        elif value >= 0.75:
            verdict = "양호"
        elif value >= 0.5:
            verdict = "보통"
        else:
            verdict = "미흡"
        print(f"  {label:<8} {value:8.2f}  {verdict:<10} {span:>22}")

    print("\n  ICC는 전체 변동 중 '사람 차이'가 차지하는 비율이다.")
    print("  0.75 이상 양호, 0.9 이상 우수로 본다.")


def report_consistency(rows: list[dict]) -> None:
    """같은 지표를 여러 부위에서 잰 값들이 서로 맞물리는가."""
    print("\n" + "=" * 62)
    print("3. 내적 일관성 — 홍조 부위별 지수")
    print("=" * 62)

    items = []
    for key in REDNESS_REGIONS:
        values = [float(r[key]) for r in rows if key in r]
        if len(values) != len(rows):
            print("  부위별 지수가 일부 사진에 없어 계산을 건너뜁니다.")
            return
        items.append(values)

    alpha = cronbach_alpha(items)
    if alpha is None:
        print("  계산 불가 (표본 부족)")
        return
    print(f"  Cronbach alpha = {alpha:.2f}   (0.7 이상이면 일관적)")

    overall = [float(r["redness_index"]) for r in rows]
    for key, values in zip(REDNESS_REGIONS, items):
        print(f"    {key:18} ~ 전체홍조  r = {pearson(values, overall):+.2f}")
    print(f"    좌우 볼 대칭            r = {pearson(items[1], items[2]):+.2f}")


def report_correlations(rows: list[dict]) -> None:
    """서로 다른 지표가 사실은 같은 것을 재고 있지 않은가."""
    print("\n" + "=" * 62)
    print("4. 판별 타당도 — 지표 간 상관")
    print("=" * 62)

    series = {}
    for key, label in RAW_METRICS:
        values = [float(r[key]) for r in rows if key in r]
        if len(values) == len(rows):
            series[label] = values

    labels = list(series)
    flagged = []
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            r = pearson(series[a], series[b])
            mark = ""
            if not math.isnan(r) and abs(r) >= 0.7:
                mark = "  <-- 확인 필요"
                flagged.append((a, b, r))
            print(f"  {a:<8} ~ {b:<8} r = {r:+.2f}{mark}")

    if flagged:
        print("\n  상관이 0.7을 넘으면 두 지표가 사실상 같은 것을 재고 있을 수")
        print("  있습니다. 표본이 작으면 우연일 수 있으니 20명 이상에서 다시")
        print("  확인한 뒤에도 남아 있으면 로직을 손봐야 합니다.")


def save_csv(rows: list[dict], path: Path) -> None:
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n원시값을 {path} 에 저장했습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="피부 분석 신뢰성 측정")
    parser.add_argument("folder", type=Path, help="사진 폴더 ({사람ID}_{회차}.jpg)")
    parser.add_argument("--url", default="http://localhost:8000", help="API 주소")
    parser.add_argument("--out", type=Path, default=Path("reliability_raw.csv"))
    args = parser.parse_args()

    if not args.folder.is_dir():
        sys.exit(f"폴더가 없습니다: {args.folder}")

    print(f"사진 수집 — {args.folder}\n")
    rows = collect(args.folder, args.url)
    if len(rows) < 2:
        sys.exit("\n분석할 사진이 부족합니다.")

    subjects = {r["subject"] for r in rows}
    print(f"대상 {len(subjects)}명, 사진 {len(rows)}장")

    report_condition(rows)
    report_repeatability(rows)
    report_discriminability(rows)
    report_consistency(rows)
    report_correlations(rows)
    save_csv(rows, args.out)


if __name__ == "__main__":
    main()
