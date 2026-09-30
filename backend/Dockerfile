FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # 가상환경을 /app 밖에 둬서, 로컬 개발 시 코드 볼륨 마운트가 덮어쓰지 않게 한다
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# OpenCV 런타임 의존 라이브러리.
# mediapipe가 headless가 아닌 opencv를 함께 설치해서 libGL을 찾는다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 설치 (코드만 바뀌면 이 레이어는 캐시 재사용)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .

RUN chmod +x scripts/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
