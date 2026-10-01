import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import service
from app.auth.deps import CurrentUser
from app.auth.schemas import LoginRequest, OAuthTokenOut, SignupRequest, TokenOut, UserOut
from app.auth.tokens import create_access_token
from app.config import Settings
from app.db.models import User
from app.dependencies import DbSession, SettingsDep
from app.envelope import Envelope, error_responses, ok
from app.ratelimit.deps import enforce_auth_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_for(user: User, settings: Settings) -> TokenOut:
    access_token, expires_in = create_access_token(user.id, settings)
    return TokenOut(
        access_token=access_token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post(
    "/signup",
    status_code=201,
    response_model=Envelope[TokenOut],
    responses=error_responses(409, 422, 429),
    dependencies=[Depends(enforce_auth_limit)],
)
def signup(body: SignupRequest, session: DbSession, settings: SettingsDep) -> Envelope[TokenOut]:
    """Creates an account and returns an access token for it."""
    user = service.register_user(session, body.email, body.password)
    logger.info("auth.signed_up", extra={"user_id": str(user.id)})
    return ok(_token_for(user, settings))


@router.post(
    "/login",
    response_model=Envelope[TokenOut],
    responses=error_responses(401, 422, 429),
    dependencies=[Depends(enforce_auth_limit)],
)
def login(body: LoginRequest, session: DbSession, settings: SettingsDep) -> Envelope[TokenOut]:
    """Exchanges an email and password for an access token."""
    user = service.authenticate(session, body.email, body.password)
    logger.info("auth.logged_in", extra={"user_id": str(user.id)})
    return ok(_token_for(user, settings))


@router.post(
    "/token",
    response_model=OAuthTokenOut,
    responses=error_responses(401, 422, 429),
    dependencies=[Depends(enforce_auth_limit)],
)
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: DbSession,
    settings: SettingsDep,
) -> OAuthTokenOut:
    """OAuth2 password flow behind the Authorize button in /docs. Put your email in `username`."""
    user = service.authenticate(session, form.username, form.password)
    access_token, _ = create_access_token(user.id, settings)
    return OAuthTokenOut(access_token=access_token)


@router.get("/me", response_model=Envelope[UserOut], responses=error_responses(401))
def me(user: CurrentUser) -> Envelope[UserOut]:
    """The account the token belongs to."""
    return ok(UserOut.model_validate(user))
