# 피부 분석 검증 스크립트 (임시)

피부 분석 로직(`app/services/skin_analysis.py`)의 신뢰도·타당도를 실험으로 확인하는 스크립트 모음이다.

- **앱 코드는 이 폴더를 참조하지 않는다.** 이 폴더가 앱 코드를 읽기만 한다.
- 서버·DB 없이 분석 함수를 직접 호출한다.
- 사진은 저장하지 않는다. 결과는 `output/` 폴더에 수치(CSV)로만 남는다. `output/`은 git에 올라가지 않는다.
- **다 쓰고 나면 `scripts/validation` 폴더를 통째로 지우면 된다.** 다른 파일은 수정할 필요가 없다.

| 파일 | 용도 |
|---|---|
| `manipulation_report.py` | 반복 촬영으로 측정 잡음(MDC) 계산, 조작 실험(파운데이션·블러셔·립틴트 점·따뜻한 수건) 전후 비교, 지표 간 간섭, 장소 강건성 |
| `synthetic_trouble.py` | 크기·붉은 정도를 아는 점을 사진에 합성해 트러블 검출률과 최소 검출 크기 측정 (사람 불필요) |
| `skin_tone_probe.py` | 피부톤(ITA°·색상각) 시험 계산, 보정 방식(없음·그레이월드·흰자위) 비교, 가상 조명 변화에 대한 안정성 |
| `_common.py` | 공용 도구 (분석 호출, 통계, CSV) |

## 실행 (backend 폴더에서, 프로젝트 가상환경 사용)

```powershell
# 조작 실험 분석
.venv\Scripts\python scripts/validation/manipulation_report.py 실험사진폴더
# 이미 분석한 결과로 표만 다시 보기
.venv\Scripts\python scripts/validation/manipulation_report.py --from-csv scripts/validation/output/manipulation_raw.csv

# 피부톤 시험 (사진 1장당 1초 미만)
.venv\Scripts\python scripts/validation/skin_tone_probe.py 사진폴더

# 합성 트러블 (깨끗한 사진 폴더, 사진 1장당 약 1분)
.venv\Scripts\python scripts/validation/synthetic_trouble.py 깨끗한사진폴더
```

카메라 프로필과 최소 얼굴 너비는 `backend/.env` 값을 그대로 쓴다. 바꾸려면 `--profile webcam`처럼 지정한다.

## 조작 실험 파일명 규칙

`{사람}_{단계}_{회차}.jpg` — 예: `A_rep_1.jpg`, `B_dot3_2.jpg` (사람 ID에 밑줄 금지)

| 단계 | 내용 | 장수 |
|---|---|---|
| `rep` | 맨얼굴 반복 촬영, **매번 일어났다 다시 앉기** | 5 |
| `loc1`, `loc2` | 다른 장소에서 맨얼굴 | 각 3 |
| `base` | 맨얼굴 (조작 실험 시작) | 3 |
| `found` | 한 톤 밝은 파운데이션 전체 | 3 |
| `blush` | 양쪽 볼에 블러셔 작은 얼룩 여러 곳 (한쪽만 바르면 조명 치우침으로 거절됨) | 3 |
| `dot3` | 볼에 립틴트 점 3개 (지름 3~4mm) | 3 |
| `dot6` | 점 6개 | 3 |
| `red0` → `redhot` → `red20` | 클렌징 후 진정된 상태 → 따뜻한 수건 2분 직후 → 20분 후 | 각 3 |

화장은 base → found → blush → dot3 → dot6 순으로 쌓고, 클렌징은 마지막에 한 번만 한다.
홍조 실험은 클렌징 후 충분히 진정시킨 다음 따로 한다.

## 결과 해석

- **MDC배수 > 1**이고 방향이 맞으면 통과다. 측정 잡음보다 큰 실제 변화라는 뜻이다.
- 트러블은 깨끗한 피부에서 반복 측정값이 모두 0이면 MDC가 0이 되어 배수가 `∞`로 표시된다. 이때는 원시값 차이 자체를 본다.
- 4명 전원 통과는 "4명 모두 측정 잡음을 넘어 기대 방향으로 변했다"는 근거다. 통계적 유의성(p<0.05)에는 약간 못 미친다(부호검정 p≈0.06).
