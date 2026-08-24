from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .errors import GuardianError
from .models import IdentityState, Role, User
from .schemas import (
    BootstrapRequest,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserResponse,
    UserStatusUpdate,
)
from .security import (
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)

router = APIRouter(prefix="/api/v1")
BOOTSTRAP_STATE_KEY = "bootstrap_completed"


def _token_pair(user: User, request: Request) -> TokenPair:
    return TokenPair(
        access_token=request.app.state.tokens.create_access_token(user),
        refresh_token=request.app.state.tokens.create_refresh_token(user),
    )


@router.post("/auth/bootstrap", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def bootstrap_identity(
    payload: BootstrapRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> User:
    bootstrap_state = session.get(IdentityState, BOOTSTRAP_STATE_KEY)
    existing_user = session.execute(select(User.id).limit(1)).first()
    if bootstrap_state is not None or existing_user is not None:
        raise GuardianError(
            status.HTTP_409_CONFLICT,
            "identity.bootstrap_already_completed",
            "Identity bootstrap has already been completed",
        )

    user = User(
        email=str(payload.email).strip().lower(),
        display_name=payload.display_name.strip(),
        role=Role.PLATFORM_ADMIN,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    session.add(user)
    session.add(IdentityState(key=BOOTSTRAP_STATE_KEY, value="true"))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(
            status.HTTP_409_CONFLICT,
            "identity.bootstrap_already_completed",
            "Identity bootstrap has already been completed",
        ) from exc
    session.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenPair)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> TokenPair:
    email = str(payload.email).strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise GuardianError(
            status.HTTP_401_UNAUTHORIZED,
            "identity.invalid_credentials",
            "Invalid credentials",
        )
    if not user.is_active:
        raise GuardianError(
            status.HTTP_403_FORBIDDEN,
            "identity.user_disabled",
            "User account is disabled",
        )
    return _token_pair(user, request)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> TokenPair:
    claims = request.app.state.tokens.decode(payload.refresh_token, "refresh")
    user = session.get(User, claims["sub"])
    if user is None:
        raise GuardianError(
            status.HTTP_401_UNAUTHORIZED,
            "identity.invalid_token",
            "Invalid token",
        )
    if not user.is_active:
        raise GuardianError(
            status.HTTP_403_FORBIDDEN,
            "identity.user_disabled",
            "User account is disabled",
        )
    return _token_pair(user, request)


@router.get("/users/me", response_model=UserResponse)
def current_user(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.PLATFORM_ADMIN)),
) -> User:
    user = User(
        email=str(payload.email).strip().lower(),
        display_name=payload.display_name.strip(),
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(
            status.HTTP_409_CONFLICT,
            "identity.email_already_exists",
            "A user with this email already exists",
        ) from exc
    session.refresh(user)
    return user


@router.get("/users", response_model=list[UserResponse])
def list_users(
    session: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.PLATFORM_ADMIN)),
) -> list[User]:
    return list(session.scalars(select(User).order_by(User.email)).all())


@router.patch("/users/{user_id}/status", response_model=UserResponse)
def set_user_status(
    user_id: str,
    payload: UserStatusUpdate,
    session: Session = Depends(get_db),
    _: User = Depends(require_roles(Role.PLATFORM_ADMIN)),
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise GuardianError(
            status.HTTP_404_NOT_FOUND,
            "identity.user_not_found",
            "User not found",
        )
    user.is_active = payload.is_active
    session.commit()
    session.refresh(user)
    return user
