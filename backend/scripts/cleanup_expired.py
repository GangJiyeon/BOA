"""만료 데이터 정리 수동 실행 (매일 새벽 4시 자동 실행과 같은 함수)

실행: cd backend >> docker compose exec api python scripts/cleanup_expired.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.cleanup import run_cleanup


def main() -> None:
    counts = run_cleanup()
    for table, n in counts.items():
        print(f"{table}: {n}건 삭제")


if __name__ == "__main__":
    main()
