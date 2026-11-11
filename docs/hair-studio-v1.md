# AI 헤어 스튜디오 v1

추천받은 헤어스타일을 사용자 사진에 합성하고, 32가지 머리색을 즉시 바꿔 보는 기능

## 흐름

1. 프론트: 헤어 추천 결과 + 얼굴형 분석에 쓴 정면 사진(첫 장)으로 `POST /api/studio/hair-renders`
2. 백엔드(백그라운드)
   - Flash(`gemini-3.1-flash-image`) 1회, 2K 출력: 원본 세 장 나란히(16:9 등 출력 비율에 맞게 바깥 패딩) + 카탈로그 스타일 사진 → 어두운 갈색(레벨 4) `mid`, 중간 갈색(레벨 7) `brown`, 밝은 애쉬 플래티넘 `light`
     - 칸당 원본의 약 1.4배 해상도, 세 칸 머리 겹침 0.93~0.97
     - 늘린(패딩) 부분은 흐려서 넣음 (가장자리 복사 줄무늬를 AI가 따라 그려 정수리 위에 섞임)
     - 두 칸을 새로 그리게 하면 얼굴을 정면으로 돌려 구도가 바뀜 → 이미 나란히 놓인 두 사진을 고치게 함 (얼굴 위치 차이 2~4px)
     - 두 베이스 모두 원본 위에 합성 (밝은 쪽을 어두운 베이스 위에 붙이면 가장자리에 어두운 머리가 비쳐 염색 때 검은 외곽선)
     - 칸끼리 머리 겹침 0.85 미만이면 한 번 더 생성, 밝은 쪽 실루엣은 어두운 쪽에 맞춤(`lock_silhouette`, 어두운 쪽에만 머리인 곳만 채움)
     - 카탈로그 사진은 사람 밖 배경을 흰색으로 덮어 보냄 (표에서 잘라 옆 칸 이름표가 섞임, "Flower perm" 글자 때문에 생머리가 곱슬로 생성된 적 있음)
   - 원본 사진 속 머리색을 `hair_hex`로 저장 (원본 사진 대신 색만)
   - 원본 사진 위에 AI 결과의 머리카락만 옮겨 붙임 (눈~턱 얼굴·얼굴형은 원본 픽셀 그대로)
     - 분할 모델이 놓친 피부 위 얇은 원래 머리 가닥(원본이 AI 피부보다 확연히 어두운 곳)도 AI 결과로 (눈꼬리 옆 잘린 가닥 자국)
     - 원래 머리에 가려졌던 볼·턱은 AI 결과로 채움 → AI가 좁힌 턱선을 원본 윤곽에 맞춰 조각별 변형
     - 윗눈꺼풀 위(이마·눈썹·앞머리)는 AI 결과 통째로 (얇은 앞머리 가닥이 잘리지 않게), 피부 톤은 원본에 맞춤
     - AI가 다시 그린 배경은 원본 배경 톤에 맞춤
     - 턱 아래(몸·옷)는 몸 기준으로 한 번 더 정렬 (AI가 몸을 몇 % 작게·옆으로 그려 원래 긴 머리 자리의 어깨·팔이 어긋남)
     - 턱 아래는 몸 기준으로 맞춘 AI 결과 통째로 (원본 피부와 AI 피부를 이어 붙이면 톤·그늘 차이로 경계선이 보임), 옷 디테일은 AI 버전
   - 베이스별 머리 마스크 PNG 생성 (MediaPipe selfie multiclass), 밝은 베이스는 guided filter로 가닥 경계까지 + 한 칸 넓히고 가장자리 더 칠한 뒤 살짝 흐림 (덜 칠해진 가장자리에 플래티넘이 남아 흰 테두리, 흰 배경에서 심함)
3. 프론트: `GET /api/studio/hair-renders/{id}` 2초 폴링 → 완료되면 캔버스에서 색 변경
   - 기본은 어두운 갈색, "원래 머리색" 칸(`hair_hex`) + 32색 프리셋 (카키·올리브·민트·코랄·골드·라벤더·애쉬퍼플·블루그레이는 칠한 느낌이 강해 뺌)
   - 가장 가까운 베이스에서 변경: L 30 미만 `mid`, 30~52 `brown`, 그 밖 `light` (베이스에서 멀리 칠할수록 외곽·떡짐이 드러남), 밝은 베이스에서 어둡게 내릴 때는 명암 그대로
   - 세 베이스를 합성 완료 시 함께 제공하므로 모든 프리셋은 추가 AI 요청 없이 바로 변경
   - 아주 어두운 색(L < 25)은 윤기(밝은 쪽 명암)는 그대로, 그림자만 눌러 칠한 덩어리처럼 보이지 않게

## 비용·시간 (1회)

| 단계 | 모델 | 비용 | 시간 |
|---|---|---|---|
| 스타일 합성 (세 베이스, 2K) | Flash | 약 $0.10 | 약 20초 |
| 머리 옮겨 붙이기·마스크·색 변경 | 로컬 | 0 | 수 초 |

1회 약 $0.10 (약 140원, 2K 출력 1,680토큰), 모델은 `STUDIO_STYLE_MODEL`로 변경

## API

- `POST /api/studio/hair-renders` (multipart: `photo`, `style_id`, `run_id?`) → 202 `HairRenderRead`
  - 촬영 동의 필요(`require_analysis_actor`), 비회원 하루 `GUEST_DAILY_LIMIT_STUDIO`회
  - 얼굴 없는 사진은 AI 호출 전 422
  - 원본 사진은 저장 안 함
- `GET /api/studio/hair-renders/{id}` → 본인(같은 회원·비회원 세션) 결과만, 아니면 404
  - `mid`, `brown`, `light` 베이스와 `hair_hex` (합성 완료 시 세 베이스 제공)
- `GET /api/guest/quota` 응답에 `studio` 추가

## 저장

- 결과 이미지: `backend/static/studio/{asset_dir}/` (mid.jpg, mid_mask.png / 요청 시 light.jpg, light_mask.png)
  - asset_dir은 추측 불가 토큰, gitignore 처리
  - 보관 `STUDIO_KEEP_DAYS`(기본 7일), 새벽 정리 작업에서 행·폴더 삭제
  - 배포 시 S3로 옮길 예정
- 분할 모델: `backend/ml_assets/` (첫 사용 때 자동 다운로드, gitignore)
- 개발용 `STUDIO_DEBUG=true`: 원본 사진·AI 원본 결과를 `backend/studio_debug/{asset_dir}/`에 PNG로 저장 (static 밖, gitignore, 자동 정리 없음)
  - 합성 조정을 AI 재호출 없이 하기 위함, 배포 시 false

## 스키마 (로컬 DB에 직접 실행)

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

Alembic 마이그레이션: `f1a2b3c4d5e6_create_hair_renders`, `a7b8c9d0e1f2_add_hair_render_light_base`, `b2c3d4e5f6a7_drop_hair_render_light_state` (서버 배포 후용)

## 알려진 한계

- 프리셋은 사진 1장·스타일 몇 개로 맞춘 값, 다른 피부톤·조명·남성 숏컷 검증 필요
- 파스텔 계열은 밝은 베이스라 숱 적은 앞머리에 틈이 살짝 보일 수 있음
- 프리셋 보정값(tex·chroma·lOff)은 현재 어두운 mid·중간 brown·밝은 light 베이스 기준
- 염색 마스크가 저해상도(256×256) 분할 결과라 비치는 앞머리는 가닥 사이 피부까지 칠해짐 (어두운 색에서 떡져 보임)
- AI가 앞머리를 시스루로 그리는 경우 있음 (카탈로그 사진이 약 90×110px 썸네일이라 디테일 전달 부족, 원본 사진 다시 받기 필요), 눈썹은 AI 결과 사용
- 외부 AI(Google)로 얼굴 사진 전송 → 약관 항목 추가 필요
