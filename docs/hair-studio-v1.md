# AI 헤어 스튜디오 v1

추천받은 헤어스타일을 사용자 사진에 합성하고, 40가지 머리색을 즉시 바꿔 보는 기능

## 흐름

1. 프론트: 헤어 추천 결과 + 얼굴형 분석에 쓴 정면 사진(첫 장)으로 `POST /api/studio/hair-renders`
2. 백엔드(백그라운드)
   - Flash(`gemini-3.1-flash-image`): 원본 + 카탈로그 스타일 사진 → 밝은 애쉬 블론드 베이스
   - Lite(`gemini-3.1-flash-lite-image`): 밝은 베이스 → 중간 브라운 베이스 (색만 변경)
   - 원본 사진 위에 AI 결과의 머리카락만 옮겨 붙임 (얼굴·얼굴형·옷은 원본 픽셀 그대로)
   - 베이스별 머리 마스크 PNG 생성 (MediaPipe selfie multiclass)
3. 프론트: `GET /api/studio/hair-renders/{id}` 2초 폴링 → 완료되면 40색 프리셋으로 캔버스에서 색 변경 (AI 추가 호출 없음)
   - 어두운 색(L ≤ 55)은 중간 베이스, 밝은 색은 밝은 베이스에서 변경 (앞머리 끊김 방지)

## 비용·시간 (1회)

| 단계 | 모델 | 비용 | 시간 |
|---|---|---|---|
| 스타일 합성 | Flash | 약 $0.067 | 약 10초 |
| 중간 베이스 | Lite | 약 $0.034 | 약 4초 |
| 머리 옮겨 붙이기·마스크·색 변경 | 로컬 | 0 | 수 초 |

합계 1회 약 $0.10 (약 140원), 모델은 `STUDIO_STYLE_MODEL`·`STUDIO_RECOLOR_MODEL`로 변경

## API

- `POST /api/studio/hair-renders` (multipart: `photo`, `style_id`, `run_id?`) → 202 `HairRenderRead`
  - 촬영 동의 필요(`require_analysis_actor`), 비회원 하루 `GUEST_DAILY_LIMIT_STUDIO`회
  - 얼굴 없는 사진은 AI 호출 전 422
  - 원본 사진은 저장 안 함
- `GET /api/studio/hair-renders/{id}` → 본인(같은 회원·비회원 세션) 결과만, 아니면 404
- `GET /api/guest/quota` 응답에 `studio` 추가

## 저장

- 결과 이미지: `backend/static/studio/{asset_dir}/` (light.jpg, light_mask.png, mid.jpg, mid_mask.png)
  - asset_dir은 추측 불가 토큰, gitignore 처리
  - 보관 `STUDIO_KEEP_DAYS`(기본 7일), 새벽 정리 작업에서 행·폴더 삭제
  - 배포 시 S3로 옮길 예정
- 분할 모델: `backend/ml_assets/` (첫 사용 때 자동 다운로드, gitignore)

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
	CONSTRAINT pk_hair_renders PRIMARY KEY (id),
	CONSTRAINT fk_hair_renders_run_id_hair_rec_runs FOREIGN KEY(run_id) REFERENCES hair_rec_runs (id) ON DELETE SET NULL,
	CONSTRAINT fk_hair_renders_style_id_hair_style_catalog FOREIGN KEY(style_id) REFERENCES hair_style_catalog (style_id),
	CONSTRAINT uq_hair_renders_asset_dir UNIQUE (asset_dir)
);
CREATE INDEX ix_hair_renders_created_at ON hair_renders (created_at);
CREATE INDEX ix_hair_renders_guest_id ON hair_renders (guest_id);
CREATE INDEX ix_hair_renders_user_id ON hair_renders (user_id);
```

Alembic 마이그레이션: `f1a2b3c4d5e6_create_hair_renders` (서버 배포 후용)

## 알려진 한계

- 프리셋은 사진 1장·스타일 몇 개로 맞춘 값, 다른 피부톤·조명·남성 숏컷 검증 필요
- 파스텔 계열은 밝은 베이스라 숱 적은 앞머리에 틈이 살짝 보일 수 있음
- 외부 AI(Google)로 얼굴 사진 전송 → 약관 항목 추가 필요
