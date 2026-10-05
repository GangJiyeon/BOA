# 성분 함량 원문 보존 v1

기준: rules-db-v1 + quality-v1 적용 상태. 이 문서는 실제 DB 쓰기 전 설명과 단계별 실행 절차다.
새 테이블 두 개와 원문 이관 도구를 추가한다. 기존 제품/성분/연결/피부/헤어/추천 규칙은 수정하지 않는다.
함량 문자열을 농도로 자동 확정하거나 추천 점수에 반영하지 않는다.

## 왜 별도 테이블인가

첨부 SQLite는 대표 처방에 성분 원문 76,990행을 보유하며, 기존 연결 테이블은 이를 제품-성분별
76,970개로 합친다. 같은 성분이 여러 위치에 나타나는 20행을 버리지 않으려면 기존 연결에
함량 문자열 하나만 추가하는 것으로는 충분하지 않다. 원문 관측을 별도 이력으로 보존한다.

| 새 테이블 | 내용 | 이번 스냅샷을 처음 저장할 때 |
|---|---|---:|
| cosmetic_observation_batches | 논리 스냅샷 식별자, 최초 원본 파일 해시, 저장 내용 해시, 이관 버전, 건수, 생성 시각 | 1행 |
| product_ingredient_observations | 대상 제품/성분 연결, 원본 제품/성분/처방 ID, 위치, URL, 원문 해시, 성분 원문, 함량 원문 | 76,990행 |

함량 원문이 있는 행은 2,587개, 미표기는 74,403개다. 모든 행의 review_status는 `unreviewed`다.
빈 문자열을 0%로 해석하지 않으며 `%`/`ppm`/`ppb`를 자동 환산하지 않는다.
원문에 쓰인 농도가 순수 성분인지 복합 원료인지, 질량비인지 부피비인지 이 데이터만으로 확정하지 않는다.

관측 행은 기존 product_ingredients의 복합 키를 참조한다. 참조 중인 연결을 삭제하면 FK가
이를 막으며, 자동 연쇄 삭제는 없다. 현재 추천 API는 이 새 테이블을 조회하지 않으므로
마이그레이션 전이나 원문 이관 전에도 기존 추천 동작은 유지된다.

## 안전장치

- 원본은 SQLite URI `mode=ro`와 `query_only`로 읽고 읽기 전후 파일 해시를 대조한다.
  WAL이 있으면 중단한다. WAL 파일을 임의 삭제하지 말고 수집 프로그램에서 일관된 백업을 만든다.
- source_product_id가 PostgreSQL product_id와 같다고 가정하지 않는다.
  정확한 source_url이 유일하게 대응해야 하며 이름·브랜드·성분 원문·정규화 상태까지 대조한다.
- 성분명은 정확히 일치해야 한다. 공백/Unicode 정규화 후 같은 이름이 여러 개면 추측하지 않는다.
- 원본 제품의 기존 제품-성분 연결 집합이 정확히 같아야 한다. 누락/추가 연결은 자동 수정하지 않는다.
- 원본 제품/성분 전체를 검사하므로 다른 버전의 파일이면 안전하게 중단할 수 있다.
- 기본 dry-run은 조회만 한다. PostgreSQL CLI 경로에서는 트랜잭션도 READ ONLY로 설정한다.
  테이블이 아직 없어도 대응 관계와 예상 건수를 검사할 수 있다.
- --apply도 먼저 같은 검사를 통과해야 한다. 한 트랜잭션 안에서 새 테이블에만 INSERT한다.
  저장 직후 전체 관측 내용 해시를 재검증한다. 실패 시 배치와 관측 INSERT를 모두 롤백한다.
- 재실행은 논리 스냅샷 식별자와 저장 내용 해시로 검증하고 unchanged를 반환한다.
  파일의 물리 배치만 바뀌고 읽은 논리 내용이 같으면 새 이력을 중복 삽입하지 않는다.
- 부분 삭제·함량 원문 수정이 감지되면 중단한다. 덮어쓰기/자동 복구/과거 이력 삭제 기능은 없다.
- 동시 이관 시 같은 배치의 중복 저장은 기본키 제약으로 실패/롤백된다. 첫 실행 완료 후 재검사한다.

## 1단계: 코드 적용과 조회 전용 검사 — 지금 실행할 범위

`boa-cosmetic-observations-v1.patch`는 quality-v1 위에 추가하는 증분 패치다.
이전 패치를 다시 적용하지 않는다. 각 명령이 실패하면 다음 단계로 진행하지 않는다.

```powershell
cd C:\Users\USER\Desktop\BOA-git
git apply --check "$HOME\Downloads\boa-cosmetic-observations-v1.patch"
# 검사 성공 시에만 실행
git apply "$HOME\Downloads\boa-cosmetic-observations-v1.patch"
cd backend
docker compose exec api python -m unittest discover -s tests -v
docker compose exec api python scripts/import_cosmetic_observations.py data/beauty_catalog.db
```

현재 PC에 위 파일이 있는지는 직접 확인하지 못했다. 컨테이너 경로는 `/app/data/beauty_catalog.db`다.
원본이 없다는 오류가 나면 빈 파일을 만들거나 import_cosmetics.py를 다시 실행하지 않는다.
원래 사용한 수집 DB 파일 위치부터 확인한다. 이 도구는 원본이 없으면 DB 연결 전에 중단한다.

첨부 스냅샷과 현재 카탈로그가 같고 새 테이블은 아직 없을 때 기대하는 핵심 출력:

```json
{
  "action": "dry_run",
  "migration_required": true,
  "required_revision": "d0610a1b2c3d",
  "source_products": 2584,
  "source_ingredients": 3099,
  "observations": 76990,
  "amounts_present": 2587,
  "amounts_not_reported": 74403,
  "unique_product_ingredient_pairs": 76970,
  "would_insert_batches": 1,
  "would_insert_observations": 76990,
  "existing_catalog_writes": 0,
  "recommendation_rules_changed": false
}
```

`migration_required: true`는 검사 오류가 아니라 아직 빈 보조 테이블을 만들지 않았다는 뜻이다.
이 단계까지는 실제 DB 스키마/데이터를 변경하지 않는다. 출력 확인 후 2단계를 진행한다.

## 2단계: 검토 후 별도로 실행하는 DB 쓰기

마이그레이션 `c0510a1b2c3d → d0610a1b2c3d`는 새 빈 테이블 두 개와 인덱스/제약을 만들고
alembic_version을 갱신한다. 데이터 INSERT는 이후 --apply 명령에서만 한다.
사전 검사 결과와 아래 쓰기 범위를 확인하고, DB 백업/복구 방법을 확보한 후 진행한다.

팀원의 다른 마이그레이션을 이미 반영했다면 아래 버전을 무조건 실행하지 말고
`alembic current`와 `alembic heads` 출력으로 분기 상태부터 확인한다.

```powershell
docker compose exec api alembic current
docker compose exec api alembic heads
# 예상 계보 확인 후, 새 스키마만 생성
docker compose exec api alembic upgrade d0610a1b2c3d
# 마이그레이션 후에도 다시 조회 전용 검사
docker compose exec api python scripts/import_cosmetic_observations.py data/beauty_catalog.db
# 위 결과 검토 후에만 실제 이력 저장
docker compose exec api python scripts/import_cosmetic_observations.py data/beauty_catalog.db --apply
# 재검사: action=unchanged, would_insert_observations=0 기대
docker compose exec api python scripts/import_cosmetic_observations.py data/beauty_catalog.db
```

--apply 오류 시 데이터 트랜잭션은 롤백되지만 앞서 생성한 빈 스키마는 남는다.
다운그레이드는 관측 이력 전체를 삭제하므로 자동 복구 명령으로 안내하지 않는다.
복구가 필요하면 당시 원본/백업과 저장 이력을 확인한 후 삭제 범위를 별도로 검토해야 한다.

## 개발 측 검증 범위

- 독립 SQLite 테스트 77개: 기존 55개 + 원문 이관 22개. 사용자 PostgreSQL 미접속.
- 누락/추가 연결, URL 중복, 성분명 충돌, 원문 불일치, 잘못된 처방 소유자, WAL,
  재실행, 부분 삭제, 내용 변경, INSERT 실패, 저장 후 해시 불일치의 중단/롤백을 검증했다.
- 모델과 마이그레이션의 일치, FK/상태 제약, downgrade 후 기존 제품/연결 보존을 검증했다.
- 실제 첨부 2,584제품·3,099성분·76,990원문을 메모리 DB에 재현했다.
  원본과 다른 숫자 ID로 대응시켰으며 저장 전후 기존 카탈로그 전체 내용 해시가 같았다.
- PostgreSQL용 offline DDL 생성 성공. 실제 PostgreSQL DDL/이관 실행은 아직 미확인.
- 이번 변경은 프론트/추천 규칙을 수정하지 않는다. 실제 UI 검수는 이번 작업 범위가 아니다.

재현 도구:

```sh
# 원본 자체 집계, 표준 라이브러리만 사용
python scripts/audit_cosmetic_amounts.py /path/to/beauty_catalog.db
# 메모리 DB에서 스키마 생성/이관/재실행 검증. 사용자 DATABASE_URL 사용 안 함
python scripts/verify_cosmetic_observations.py /path/to/beauty_catalog.db
```

## 그 다음

이 기능은 원문을 보존하는 기반이다. 추천 품질이 자동으로 개선되는 패치가 아니다.
다음 단계는 단위/적용 대상/제조사 표기의 검토 상태를 별도로 관리하고, 확인된 조건과
미확인 조건을 구분한 규칙 v2를 검수하는 것이다. 함량이 높을수록 좋다는 가중치는 만들지 않는다.
