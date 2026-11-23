# AI 헤어 스튜디오 v1

2026-11-20 로컬 코드 기준. 구현 개요는 이 문서, 함수별 학습 설명은 [헤어 합성 학습 가이드](hair-synthesis-study-guide.md)를 참고한다.

직접 업로드한 사진과 카탈로그 스타일 또는 헤어 추천 결과를 사용해 합성하고, 브라우저에서 32가지 프리셋으로 머리색을 바꾸는 기능. 추천 분석을 먼저 해야만 사용할 수 있는 구조는 아니다.

- 현재 구현을 설명하는 본문과 과거 실험 수치를 구분했다. 외부 AI의 최신 가격·모델 지원·생성 속도를 새로 측정한 문서는 아니다.

## 흐름

1. 프론트: 직접 업로드 사진 + 카탈로그 스타일, 또는 헤어 추천 결과 + 분석에 쓴 정면 사진(첫 장)으로 `POST /api/studio/hair-renders`. `run_id`는 추천에서 가져올 때만 보낸다.
2. 백엔드 요청 처리: 인증·스타일·사용량 검사 후 사진을 디코딩한다. 얼굴 없음, 기울기 10° 초과, yaw 근사 지표 0.35 초과, 축소 후 얼굴 폭 120px 미만이면 AI 호출 전에 422. 이미지가 10MB를 넘으면 413. 통과하면 pending 행 저장 후 202를 반환하고 백그라운드 작업을 등록한다.
3. 백그라운드 합성
   - 원본 사진 한 장에 출력 비율에 맞는 패딩을 넣고 패딩 영역만 흐리게 처리한다. 카탈로그 참조 사진은 인물 밖을 흰색으로, 눈썹 아래 얼굴 피부를 회색으로 가린다.
   - Flash 이미지 편집을 한 번 호출해 중간 갈색(레벨 7) 결과 한 장을 1K로 생성한다. 프롬프트는 얼굴 크기·위치와 구도를 유지하고 카탈로그 스타일의 컬·질감·앞머리 숱을 따르도록 지시한다.
   - 출력을 패딩 처리된 입력 크기로 맞춘 뒤 패딩을 제거한다. 얼굴 크기 차이 12%, 기울기 4°, 좌우 돌림 차이 0.15를 초과하거나 정렬 뒤 남는 면적이 80% 미만이면 실패로 처리한다. 비회원 사용량은 실패한 작업을 제외한다.
   - 얼굴 랜드마크로 AI 결과의 회전·크기·위치를 맞춘다. 눈썹 근처부터 턱까지 원본 얼굴을 우선하고, 기존 머리로 가려진 곳과 새 앞머리·목·옷·배경에는 생성 결과를 사용한다. 피부·목·배경 톤을 보정한 뒤 다중 해상도로 경계를 섞는다.
   - MediaPipe 머리 분할 마스크에 이마의 가는 가닥을 더하고 앞머리 끝의 염색 강도를 낮춘다. 정렬 후 가장자리를 이미지와 마스크에서 같은 영역으로 잘라 `brown.jpg`와 `brown_mask.png`를 저장한다. 원래 머리색은 `hair_hex`로 저장한다.
4. 프론트는 `GET /api/studio/hair-renders/{id}`를 2초 간격으로 최대 90회 조회한다. 단계 문구는 경과 시간을 바탕으로 표시한다.
   - 브라우저는 `brown` 이미지와 마스크 한 쌍을 불러온다. 과거 결과에서 `brown`이 없으면 `light`, `mid` 순으로 대체한다.
   - 모든 프리셋과 추천색은 불러온 베이스에 적용한다. `hair_hex`가 있으면 원래 머리색도 목표색으로 선택할 수 있다. Lab 공간에서 명암을 유지하며 색을 바꾸고 머리 영역의 평균색을 목표색에 맞춰 한 번 보정한다.

## 과거 비용·시간 기록 — 현재 견적 아님

아래는 기존 개발 과정에서 적은 추정값이다. 최신 요금·환율·실측 응답 시간을 확인한 값으로 사용하지 않는다. 현재 코드의 기본 모델 설정은 `gemini-3.1-flash-image`이며 `STUDIO_STYLE_MODEL`로 변경 가능하다. 화면은 AI 생성 약 1분과 후처리 대기를 안내하기도 한다. 확실한 호출 구조는 합성 시작 시 AI 1회, 이후 색 변경 시 추가 AI 호출 없음이다.

| 단계 | 모델 | 비용 | 시간 |
|---|---|---|---|
| 스타일 합성 (세 베이스, 2K) | Flash | 약 $0.10 | 약 20초 |
| 머리 옮겨 붙이기·마스크·색 변경 | 로컬 | 추가 AI API 요금 없음. 서버·브라우저 자원 사용 | 당시 수 초 기록 |

당시에는 1회 약 $0.10(약 140원, 2K 출력 1,680토큰)으로 추정했다. 현재 비용 상한이나 보장 가격이 아니며 실패 판정도 이미 실행한 외부 요청 비용을 되돌리지 않는다.

## API

- `POST /api/studio/hair-renders` (multipart: `photo`, `style_id`, `run_id?`) → 202 `HairRenderRead`
  - 촬영 동의 필요(`require_analysis_actor`), 비회원 하루 `GUEST_DAILY_LIMIT_STUDIO`회
  - 얼굴 없는 사진은 AI 호출 전 422
  - 일반 모드는 업로드 원본 파일을 저장하지 않음. 생성 결과에는 얼굴이 포함되며 디버그 모드 예외는 아래 참고
- `GET /api/studio/hair-renders/{id}` → 본인(같은 회원·비회원 세션) 결과만, 아니면 404
  - 완료된 결과는 디스크에 있는 베이스의 이미지·마스크 URL과 `hair_hex`를 제공한다. 새 작업은 `brown`을 저장하며 `mid`와 `light`는 과거 결과용 필드다.
- `GET /api/guest/quota` 응답에 `studio` 추가

## 저장

- 결과 이미지: `backend/static/studio/{asset_dir}/`에 `brown.jpg`와 `brown_mask.png` 저장
  - asset_dir은 추측 불가 토큰, gitignore 처리
  - 보관 `STUDIO_KEEP_DAYS`(기본 7일), 새벽 정리 작업에서 행·폴더 삭제
  - 현재 로컬 static 저장. S3 이전은 미구현 계획
- 분할 모델: `backend/ml_assets/` (첫 사용 때 자동 다운로드, gitignore)
- 개발용 `STUDIO_DEBUG=true`: 원본 사진·AI 원본 결과를 `backend/studio_debug/{asset_dir}/`에 PNG로 저장 (static 밖, gitignore, 자동 정리 없음)
  - 과거 문서에 있던 `scripts/recompose_render.py`는 현재 저장소에서 확인되지 않아 실행 안내에서 제외함. `compose_bases()`는 기존 AI 출력으로 후처리를 재사용할 수 있는 함수지만 해당 CLI가 제공되는 것은 아님
  - 합성 조정을 AI 재호출 없이 하기 위함, 배포 시 false

## 스키마 참고 — 과거 수동 설치 기록

아래 SQL은 과거 테이블 구조를 설명하기 위해 보존한다. 현재 설치·변경은 [Alembic 설정](../backend/alembic.ini)과 기존 마이그레이션을 기준으로 관리하며, 이 문서를 보고 운영 DB에 수동 CREATE/ALTER를 중복 적용하지 않는다. 이번 문서 갱신에서 DB 명령은 실행하지 않았다.

```sql
CREATE TABLE hair_renders (
	id SERIAL NOT NULL,
	user_id INTEGER,
	guest_id UUID,
	run_id INTEGER,
	style_id VARCHAR(50) NOT NULL,
	status VARCHAR(20) NOT NULL,
	error VARCHAR(300),
	asset_dir VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	finished_at TIMESTAMP WITH TIME ZONE,
	hair_hex VARCHAR(7),
	CONSTRAINT pk_hair_renders PRIMARY KEY (id),
	CONSTRAINT fk_hair_renders_run_id_hair_rec_runs FOREIGN KEY(run_id) REFERENCES hair_rec_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_hair_renders_style_id_hair_style_catalog FOREIGN KEY(style_id) REFERENCES hair_style_catalog (style_id),
	CONSTRAINT uq_hair_renders_asset_dir UNIQUE (asset_dir)
);
CREATE INDEX ix_hair_renders_created_at ON hair_renders (created_at);
CREATE INDEX ix_hair_renders_guest_id ON hair_renders (guest_id);
CREATE INDEX ix_hair_renders_user_id ON hair_renders (user_id);
```

이미 테이블이 있으면 칼럼만 추가

```sql
ALTER TABLE hair_renders ADD COLUMN IF NOT EXISTS hair_hex VARCHAR(7);
```

Alembic 마이그레이션: `f1a2b3c4d5e6_create_hair_renders`, `a7b8c9d0e1f2_add_hair_render_light_base`, `b2c3d4e5f6a7_drop_hair_render_light_state` (스튜디오 스키마의 변경 이력)

## 알려진 한계

- 프리셋은 사진 1장·스타일 몇 개로 맞춘 값, 다른 피부톤·조명·남성 숏컷 검증 필요
- 염색 마스크가 저해상도(256×256) 분할 결과라 비치는 앞머리는 가닥 사이 피부까지 칠해짐 (어두운 색에서 떡져 보임)
- AI가 앞머리를 시스루로 그리는 경우 있음 (카탈로그 사진이 약 90×110px 썸네일이라 디테일 전달 부족, 원본 사진 다시 받기 필요). 현재 눈썹은 원본을 우선하고 머리가 덮는 경우 등에 예외 적용
- 외부 AI(Google)로 얼굴 사진 전송 → 약관 항목 추가 필요


## 현재 운영 범위와 남은 작업

- 결과 보관은 기본 7일이며 회원의 합성 결과도 대상. 업로드 원본 미보관과 생성된 얼굴 이미지 미보관은 다른 의미다.
- 상태 API는 소유자를 검사하지만 static 파일 URL 자체에는 같은 회원 검사가 붙지 않는다. 무작위 경로는 접근 제어와 구분한다.
- `run_id`는 현재 존재 여부만 검사한다. 비회원 결과 이관과 회원 이력 목록에는 HairRender가 포함되지 않는다.
- `BackgroundTasks`는 서버 프로세스 안에서 실행한다. 영속 큐·재시작 후 pending 복구·서버 작업 취소 API는 없다.
- 일반 정리는 결과 행·폴더를 처리하지만 `studio_debug` 원본·진단 파일은 자동 정리하지 않는다.
- 구도·각도 검사는 스타일 재현 정확도나 다양한 사용자 사진의 품질을 보장하는 검사가 아니다.
