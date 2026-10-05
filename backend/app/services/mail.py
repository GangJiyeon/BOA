"""메일 발송"""

import logging

logger = logging.getLogger("uvicorn.error")


def send_login_code(email: str, code: str) -> None:
    # TODO(배포 전): Gmail SMTP 연결, 지금은 서버 로그 출력만
    logger.info("[메일] %s 인증 코드: %s", email, code)
