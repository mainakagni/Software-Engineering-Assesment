"""The dependency that turns a bearer token into the logged-in user."""

from typing import Annotated

from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer

from app.auth.tokens import SESSION_INVALID_MESSAGE, decode_access_token
from app.db.models import User
from app.dependencies import DbSession, SettingsDep
from app.errors import UnauthorizedError
from app.logging_config import user_id_var

# auto_error=False: a missing token then goes through our own 401 and error envelope.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_current_user(
    session: DbSession,
    settings: SettingsDep,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise UnauthorizedError()
    user_id = decode_access_token(token, settings)
    user = await run_in_threadpool(session.get, User, user_id)
    if user is None:  # the account was deleted after the token was issued
        raise UnauthorizedError(SESSION_INVALID_MESSAGE)
    # This dependency is async on purpose: it runs in the request's own task, so the value is
    # visible to the endpoint and to the access log line. A sync dependency runs in a copied
    # context and the value would be lost when it returns.
    user_id_var.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
