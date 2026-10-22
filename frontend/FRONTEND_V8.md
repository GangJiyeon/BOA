# BOA 프론트엔드 v8 — Editorial

## 범위
홈을 큰 인물 이미지와 짧은 행동 버튼 중심으로 다시 구성하고, 사이드바를 상단 내비게이션으로 교체했습니다. 홈은 로고로 이동하며 피부·헤어·결과는 기본 메뉴, 키오스크·AI Studio는 더 보기 메뉴에 있습니다.

피부 입력 화면은 사진과 분석 시작을 중심으로 구성했습니다. 수분 수동 입력과 성분 제외 설정은 접어 두되 기존 입력값·검증·API 전달을 유지합니다. 사진 확대와 이동은 미리보기 전용이며 분석에는 원본이 전송됩니다.

백엔드, DB, API 형식, 점수 및 추천 로직은 변경하지 않았습니다. 원격 push/merge도 하지 않았습니다. API 응답의 실제 제품 이미지 URL은 그대로 사용합니다.

## 검증
- 프로덕션 빌드, 린트, API 클라이언트 검사 16개 통과.
- 테스트 API 응답을 연결한 Chromium에서 홈/분석 화면 1440px·390px 시각 검토.
- 사진 입력 필수, multipart 전송, 제품 카드, 필터 시 분석 재사용, 필터 오류 시 결과 유지, 일상 관리 응답, 빈 결과, 모바일 가로 넘침 및 런타임 오류 확인.
- 실제 로컬 백엔드·카메라 장치·이메일 인증은 사용자의 환경에서 확인이 필요합니다.

## 이미지
파일: frontend/public/images/boa-editorial-portrait.png
내장 이미지 생성 도구로 제작한 장식용 브랜드 이미지입니다. 실제 사용자나 분석 결과를 나타내지 않습니다. 이미지에 대한 AI 생성 표시는 홈에 포함되어 있습니다. 추가 패키지·외부 이미지 호스팅은 필요하지 않습니다.

생성 프롬프트: Premium editorial portrait photograph for BOA personal beauty analysis website. Adult Korean woman around 27, natural black hair tucked behind ears, gentle direct gaze, ivory crew-neck top, minimal makeup with real skin texture and subtle freckles. Soft daylight, warm beige background, calm Korean skincare editorial. Head fully inside frame, generous space around face, face slightly right, shoulders near bottom. No text, logos, products, UI or watermark. Decorative brand imagery, not analysis output.

## 적용
배포 ZIP의 Apply.ps1은 v7 적용 상태와 main 원본 상태를 각각 git apply --check로 확인하고, 맞는 패치 하나만 적용합니다. 기존 변경 때문에 둘 다 적용할 수 없으면 아무것도 덮어쓰지 않고 중단합니다. 임의로 reset/checkout하거나 커밋하지 않습니다.
