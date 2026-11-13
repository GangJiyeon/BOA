"""검증 스크립트 공용 도구.

이 폴더(scripts/validation)는 검증 실험용으로만 쓰고, 앱 코드는 이 폴더를 참조하지 않는다.
폴더를 통째로 지워도 서비스에는 영향이 없다.

앱의 피부 분석 함수(app.services.skin_analysis)를 직접 불러 쓰므로
API 서버나 DB를 띄우지 않아도 된다.
"""

from __future__ import annotations

import csv
import math
import os
import sys
from pathlib import Path

# ── 앱 코드 불러오기 준비 ────────────────────────────────────────────
# backend 폴더를 import 경로에 넣어 `app.services.skin_analysis`를 쓸 수 있게 한다
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import skin_analysis as sa  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# 검증에 쓰는 원시값 (점수는 구간에 눌려 미세한 변화가 안 보이므로 원시값을 쓴다)
RAW_METRICS = [
    ("mean_l_skin", "밝기"),
    ("std_l_skin", "균일도(편차)"),
    ("redness_index", "홍조"),
    ("blemish_ratio", "트러블"),
]


# ── 설정값 읽기 ──────────────────────────────────────────────────────


def _read_env_file(key: str) -> str | None:
    """backend/.env에서 값 하나를 읽는다. (다른 값은 건드리지 않는다)"""
    env_path = BACKEND_DIR / ".env"
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def default_profile() -> str:
    """서버와 같은 카메라 프로필을 쓴다: 환경변수 → .env → 기본값(phone)."""
    return os.environ.get("SKIN_CAMERA_PROFILE") or _read_env_file("SKIN_CAMERA_PROFILE") or "phone"


def default_min_face_width() -> int:
    """서버와 같은 최소 얼굴 너비를 쓴다: 환경변수 → .env → 기본값(250)."""
    value = os.environ.get("MIN_FACE_WIDTH_PX") or _read_env_file("MIN_FACE_WIDTH_PX")
    return int(value) if value else sa.DEFAULT_MIN_FACE_WIDTH


# ── 분석 호출 ────────────────────────────────────────────────────────


def analyze_bytes(image_bytes: bytes, profile: str, min_face_width: int) -> tuple[dict | None, str | None]:
    """사진 한 장을 분석해 (원시값, None) 또는 (None, 거절 코드)를 돌려준다."""
    try:
        scores, raw = sa.analyze_image_detail(
            image_bytes, min_face_width=min_face_width, camera_profile=profile
        )
    except sa.AnalysisError as e:
        return None, e.code
    raw = dict(raw)
    for code, score in scores.items():
        raw[f"score_{code}"] = score
    return raw, None


def list_images(folder: Path) -> list[Path]:
    """폴더의 사진 파일 목록 (이름순)."""
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


# ── 통계 ────────────────────────────────────────────────────────────


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs: list[float]) -> float:
    """표본표준편차. 값이 1개 이하면 0."""
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def pooled_sem(groups: list[list[float]]) -> float | None:
    """여러 그룹(사람별 반복 측정)의 측정 잡음(SEM)을 합쳐서 구한다.

    각 그룹 안의 편차제곱합을 모아 자유도로 나눈 값의 제곱근이다.
    """
    ss, df = 0.0, 0
    for g in groups:
        if len(g) < 2:
            continue
        m = mean(g)
        ss += sum((x - m) ** 2 for x in g)
        df += len(g) - 1
    if df == 0:
        return None
    return math.sqrt(ss / df)


def mdc95(sem: float) -> float:
    """최소 탐지 변화량 (95%). 두 번 측정한 값의 차이가 이보다 커야 '실제 변화'로 본다."""
    return 1.96 * math.sqrt(2) * sem


# ── 저장 ────────────────────────────────────────────────────────────


def save_csv(rows: list[dict], path: Path) -> None:
    """행 목록을 CSV로 저장한다 (엑셀에서 한글이 깨지지 않게 utf-8-sig)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n원시값을 저장했습니다: {path}")


def load_csv(path: Path) -> list[dict]:
    """save_csv로 저장한 파일을 다시 읽는다 (숫자는 float로 변환)."""
    rows = []
    with path.open(encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            parsed = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v)
                except (TypeError, ValueError):
                    parsed[k] = v
            rows.append(parsed)
    return rows
