import secrets
from datetime import timedelta

import jwt

from app.kernel.types import DomainError, Principal


class Auth:
    def __init__(self, settings, clock, directory):
        self.settings, self.clock, self.directory = settings, clock, directory

    def current_principal(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self.settings.signing_key,
                algorithms=["HS256"],
                audience="recruiter",
                issuer="recruiter-api",
                options={"require": ["sub", "exp", "iat", "aud", "iss"]},
            )
            user = self.directory.get_user(claims["sub"])
        except (jwt.PyJWTError, DomainError):
            raise DomainError("UNAUTHENTICATED", "登录已失效，请重新登录", 401) from None
        return Principal(user.id, user.name, user.roles, user.departments, user.permission_version)

    def dev_login(self, user_id: str, password: str) -> dict:
        if not self.settings.dev_auth_enabled:
            raise DomainError("NOT_FOUND", "接口不存在", 404)
        if not secrets.compare_digest(password, self.settings.dev_login_password):
            raise DomainError("UNAUTHENTICATED", "开发登录口令错误", 401)
        user = self.directory.get_user(user_id)
        now = self.clock.now()
        token = jwt.encode(
            {
                "sub": user.id,
                "iat": now,
                "exp": now + timedelta(hours=8),
                "aud": "recruiter",
                "iss": "recruiter-api",
            },
            self.settings.signing_key,
            algorithm="HS256",
        )
        return {"userId": user.id, "name": user.name, "roles": user.roles, "token": token}
