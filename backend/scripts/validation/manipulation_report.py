"""조작 실험 분석: 피부 상태를 의도적으로 바꿨을 때 점수가 기대한 방향으로 움직이는가.

사람이 적어도(4명) 할 수 있는 검증이다. 각 사람이 자기 자신의 대조군이 되어,
조작 전후의 원시값 차이가 '측정 잡음(MDC)'보다 큰지 본다.

사진 파일명 규칙
    {사람}_{단계}_{회차}.jpg        예) A_rep_1.jpg, A_base_2.jpg, B_dot3_1.jpg
    사람 ID에는 밑줄(_)을 쓰지 않는다.

단계 이름 (촬영 계획서와 같다)
    rep        반복 촬영 (매번 일어났다 앉기, 5장 권장) → 측정 잡음(MDC) 계산용
    loc1, loc2 다른 장소에서 촬영 → 장소 강건성 (rep과 비교)
    base       맨얼굴
    found      밝은 톤 파운데이션 전체          → 밝기 증가 기대
    blush      양볼에 블러셔 얼룩 여러 곳       → 균일도 편차 증가 기대
    dot3       볼에 립틴트 점 3개 (지름 3~4mm)  → 트러블 증가 기대
    dot6       점 6개                           → 트러블 더 증가 기대
    red0       홍조 실험 기준 (클렌징 후 진정된 상태)
    redhot     따뜻한 수건 2분 직후             → 홍조 증가 기대
    red20      20분 후                          → 홍조 감소 기대 (redhot 대비)
    없는 단계는 건너뛴다.

사용법 (backend 폴더에서)
    .venv\\Scripts\\python scripts/validation/manipulation_report.py 사진폴더
    .venv\\Scripts\\python scripts/validation/manipulation_report.py --from-csv scripts/validation/output/manipulation_raw.csv
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import _common as c

# ── 실험 설계 ───────────────────────────────────────────────────────
# (실험 이름, 전 단계, 후 단계, 목표 원시값, 기대 방향 +1 증가 / -1 감소)
COMPARISONS = [
    ("밝기: 파운데이션", "base", "found", "mean_l_skin", +1),
    ("균일도: 블러셔 얼룩", "found", "blush", "std_l_skin", +1),
    ("트러블: 점 0→3개", "blush", "dot3", "blemish_ratio", +1),
    ("트러블: 점 3→6개", "dot3", "dot6", "blemish_ratio", +1),
    ("홍조: 수건 직후", "red0", "redhot", "redness_index", +1),
    ("홍조: 20분 후 회복", "redhot", "red20", "redness_index", -1),
]

# 트러블 용량-반응 확인용 (단계, 점 개수)
TROUBLE_DOSE = [("blush", 0), ("dot3", 3), ("dot6", 6)]

DEFAULT_OUT = Path(__file__).resolve().parent / "output" / "manipulation_raw.csv"


# ── 수집 ────────────────────────────────────────────────────────────


def parse_name(path: Path) -> tuple[str, str, int] | None:
    """파일명에서 (사람, 단계, 회차)를 뽑는다. 규칙에 안 맞으면 None."""
    parts = path.stem.split("_")
    if len(parts) != 3 or not parts[2].isdigit():
        return None
    return parts[0], parts[1].lower(), int(parts[2])


def collect(folder: Path, profile: str, min_face_width: int) -> list[dict]:
    """폴더의 사진을 하나씩 분석해 원시값 행 목록을 만든다. (사진은 저장하지 않는다)"""
    photos = c.list_images(folder)
    if not photos:
        sys.exit(f"사진이 없습니다: {folder}")

    rows: list[dict] = []
    for path in photos:
        parsed = parse_name(path)
        if parsed is None:
            print(f"  건너뜀 (파일명 규칙 불일치): {path.name}")
            continue
        subject, stage, trial = parsed
        raw, error = c.analyze_bytes(path.read_bytes(), profile, min_face_width)
        row = {"subject": subject, "stage": stage, "trial": trial, "file": path.name}
        if error:
            row["rejected"] = error
            print(f"  거절  {path.name}  ({error})")
        else:
            row["rejected"] = ""
            row.update(raw)
            print(f"  수집  {path.name}")
        rows.append(row)
    return rows


# ── 집계 도우미 ──────────────────────────────────────────────────────


def values(rows: list[dict], subject: str, stage: str, key: str) -> list[float]:
    """특정 사람·단계의 원시값 목록 (거절된 사진 제외)."""
    return [
        float(r[key])
        for r in rows
        if r["subject"] == subject and r["stage"] == stage and not r.get("rejected") and key in r
        and r[key] != ""
    ]


def subjects_of(rows: list[dict]) -> list[str]:
    return sorted({str(r["subject"]) for r in rows})


def stages_of(rows: list[dict]) -> set[str]:
    return {str(r["stage"]) for r in rows}


# ── 보고 ────────────────────────────────────────────────────────────


def report_rejections(rows: list[dict]) -> None:
    """단계별 거절 현황. 조작 때문에 사진이 거절되면 그 실험은 해석할 수 없다."""
    print("\n" + "=" * 66)
    print("0. 수집·거절 현황")
    print("=" * 66)
    by_stage: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_stage[str(r["stage"])].append(r)
    for stage in sorted(by_stage):
        group = by_stage[stage]
        bad = [r for r in group if r.get("rejected")]
        codes = ", ".join(sorted({str(r["rejected"]) for r in bad})) or "-"
        print(f"  {stage:<8} {len(group):3}장  거절 {len(bad):2}장  ({codes})")


def compute_mdc(rows: list[dict]) -> dict[str, float | None]:
    """지표별 최소 탐지 변화량(MDC).

    rep 단계(일어났다 앉으며 반복 촬영)가 있으면 그것으로 계산한다.
    없으면 모든 단계의 같은 조건 반복 사진으로 계산하는데, 연속 촬영이라
    잡음이 작게 잡혀 MDC가 과소평가될 수 있다.
    """
    print("\n" + "=" * 66)
    print("1. 측정 잡음 — 최소 탐지 변화량(MDC95)")
    print("=" * 66)

    use_rep = "rep" in stages_of(rows)
    source = "rep 단계 (자세 다시 잡기 포함)" if use_rep else "단계별 연속 반복 사진 (과소평가 가능)"
    stages = ["rep"] if use_rep else sorted(stages_of(rows))
    print(f"  계산 근거: {source}\n")
    print(f"  {'지표':<14} {'SEM':>10} {'MDC95':>10} {'평균값':>10}")
    print("  " + "-" * 48)

    mdc: dict[str, float | None] = {}
    for key, label in c.RAW_METRICS:
        groups = [values(rows, s, st, key) for s in subjects_of(rows) for st in stages]
        groups = [g for g in groups if len(g) >= 2]
        sem = c.pooled_sem(groups)
        if sem is None:
            mdc[key] = None
            print(f"  {label:<14} {'계산 불가 (반복 사진 부족)':>32}")
            continue
        mdc[key] = c.mdc95(sem)
        avg = c.mean([v for g in groups for v in g])
        print(f"  {label:<14} {sem:10.4f} {mdc[key]:10.4f} {avg:10.4f}")

    print("\n  조작 전후 차이가 MDC보다 커야 '잡음이 아닌 실제 변화'로 본다.")
    return mdc


def ratio_text(diff: float, threshold: float | None) -> tuple[str, float | None]:
    """차이를 MDC 배수로 표시한다. MDC가 0이면 비율을 정의할 수 없어 따로 표시."""
    if threshold is None:
        return "-", None
    if threshold == 0:
        return ("∞" if diff != 0 else "0"), (float("inf") if diff != 0 else 0.0)
    r = diff / threshold
    return f"{r:+.1f}", r


def report_comparisons(rows: list[dict], mdc: dict[str, float | None]) -> list[tuple]:
    """실험별로 사람마다 전후 차이를 MDC와 비교한다."""
    print("\n" + "=" * 66)
    print("2. 조작 실험 — 기대 방향으로, 잡음보다 크게 변했는가")
    print("=" * 66)

    available = stages_of(rows)
    summary = []
    for name, before, after, key, direction in COMPARISONS:
        if before not in available or after not in available:
            continue
        print(f"\n  [{name}]  {before} → {after}  ({key}, 기대: {'증가' if direction > 0 else '감소'})")
        print(f"    {'사람':<6} {'전':>10} {'후':>10} {'차이':>10} {'MDC배수':>8}  판정")
        passed = tested = 0
        for subject in subjects_of(rows):
            pre = values(rows, subject, before, key)
            post = values(rows, subject, after, key)
            if not pre or not post:
                continue
            tested += 1
            diff = c.mean(post) - c.mean(pre)
            text, r = ratio_text(diff * direction, mdc.get(key))
            right_way = diff * direction > 0
            beyond = r is not None and r > 1
            if right_way and beyond:
                verdict, passed = "통과", passed + 1
            elif right_way:
                verdict = "방향만 맞음 (잡음 수준)"
            elif diff == 0:
                verdict = "변화 없음"
            else:
                verdict = "반대 방향"
            print(f"    {subject:<6} {c.mean(pre):10.4f} {c.mean(post):10.4f} {diff:+10.4f} {text:>8}  {verdict}")
        if tested:
            print(f"    → {passed}/{tested}명 통과")
            summary.append((name, passed, tested))
    print("\n  MDC배수: 기대 방향으로 MDC의 몇 배만큼 변했는지 (1보다 크면 통과)")
    return summary


def report_crosstalk(rows: list[dict], mdc: dict[str, float | None]) -> None:
    """한 가지만 바꿨을 때 다른 지표까지 움직이는가 (판별 타당도).

    목표 지표는 크게, 나머지는 1 미만이 이상적이다.
    """
    print("\n" + "=" * 66)
    print("3. 지표 간 간섭 — 평균 변화량 / MDC  (* = 목표 지표)")
    print("=" * 66)
    header = "".join(f"{label:>14}" for _, label in c.RAW_METRICS)
    print(f"  {'실험':<20}{header}")
    print("  " + "-" * (20 + 14 * len(c.RAW_METRICS)))

    available = stages_of(rows)
    for name, before, after, target, _ in COMPARISONS:
        if before not in available or after not in available:
            continue
        cells = []
        for key, _label in c.RAW_METRICS:
            diffs = []
            for subject in subjects_of(rows):
                pre = values(rows, subject, before, key)
                post = values(rows, subject, after, key)
                if pre and post:
                    diffs.append(c.mean(post) - c.mean(pre))
            text, _ = ratio_text(c.mean(diffs), mdc.get(key)) if diffs else ("-", None)
            mark = "*" if key == target else " "
            cells.append(f"{text + mark:>14}")
        print(f"  {name:<20}" + "".join(cells))
    print("\n  목표가 아닌 지표가 크게(절댓값 2 이상) 움직이면, 그 지표가 다른 것까지 재고 있다는 뜻이다.")


def report_dose(rows: list[dict]) -> None:
    """트러블 점 개수가 늘수록 트러블 원시값도 계속 늘어나는가."""
    available = stages_of(rows)
    if not all(stage in available for stage, _ in TROUBLE_DOSE):
        return
    print("\n" + "=" * 66)
    print("4. 트러블 용량-반응 — 점 0 → 3 → 6개")
    print("=" * 66)
    monotonic = tested = 0
    for subject in subjects_of(rows):
        means = [c.mean(values(rows, subject, stage, "blemish_ratio")) for stage, _ in TROUBLE_DOSE]
        if any(m != m for m in means):  # nan = 해당 단계 사진 없음
            continue
        tested += 1
        ok = all(a < b for a, b in zip(means, means[1:]))
        monotonic += ok
        series = " → ".join(f"{m:.4f}" for m in means)
        print(f"  {subject:<6} {series}   {'단조 증가' if ok else '단조 아님'}")
    if tested:
        print(f"  → {monotonic}/{tested}명 단조 증가")


def report_locations(rows: list[dict], mdc: dict[str, float | None]) -> None:
    """장소(조명)만 바꿨을 때 원시값이 얼마나 흔들리는가. MDC배수가 1 미만이면 강건하다."""
    loc_stages = sorted(s for s in stages_of(rows) if s.startswith("loc"))
    if not loc_stages or "rep" not in stages_of(rows):
        return
    print("\n" + "=" * 66)
    print("5. 장소 강건성 — rep 대비 변화량 / MDC  (절댓값 1 미만이면 강건)")
    print("=" * 66)
    header = "".join(f"{label:>14}" for _, label in c.RAW_METRICS)
    print(f"  {'사람·장소':<14}{header}")
    for subject in subjects_of(rows):
        for loc in loc_stages:
            cells = []
            for key, _label in c.RAW_METRICS:
                ref = values(rows, subject, "rep", key)
                cur = values(rows, subject, loc, key)
                text = ratio_text(c.mean(cur) - c.mean(ref), mdc.get(key))[0] if ref and cur else "-"
                cells.append(f"{text:>14}")
            print(f"  {subject + ' ' + loc:<14}" + "".join(cells))


def main() -> None:
    parser = argparse.ArgumentParser(description="피부 분석 조작 실험 분석")
    parser.add_argument("folder", type=Path, nargs="?", help="사진 폴더 ({사람}_{단계}_{회차}.jpg)")
    parser.add_argument("--from-csv", type=Path, help="이전에 저장한 원시값 CSV로 다시 계산 (사진 분석 생략)")
    parser.add_argument("--profile", default=c.default_profile(), help="카메라 프로필 (기본: .env 값)")
    parser.add_argument("--min-face-width", type=int, default=c.default_min_face_width())
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="원시값 CSV 저장 위치")
    args = parser.parse_args()

    # 1) 원시값 모으기: CSV 재사용 또는 사진 분석
    if args.from_csv:
        rows = c.load_csv(args.from_csv)
        for r in rows:
            r["subject"], r["stage"] = str(r["subject"]), str(r["stage"])
            r["rejected"] = "" if r.get("rejected") in ("", None) else str(r["rejected"])
    else:
        if args.folder is None or not args.folder.is_dir():
            sys.exit("사진 폴더를 지정하세요 (또는 --from-csv)")
        print(f"사진 분석 — {args.folder}  (카메라 프로필: {args.profile})\n")
        rows = collect(args.folder, args.profile, args.min_face_width)
        c.save_csv(rows, args.out)

    if not rows:
        sys.exit("분석할 사진이 없습니다.")

    # 2) 보고서 출력
    report_rejections(rows)
    mdc = compute_mdc(rows)
    summary = report_comparisons(rows, mdc)
    report_crosstalk(rows, mdc)
    report_dose(rows)
    report_locations(rows, mdc)

    # 3) 한 줄 요약 (발표 자료에 옮겨 쓰기 좋게)
    if summary:
        print("\n" + "=" * 66)
        print("요약")
        print("=" * 66)
        for name, passed, tested in summary:
            print(f"  {name:<20} {passed}/{tested}명 통과")


if __name__ == "__main__":
    main()
