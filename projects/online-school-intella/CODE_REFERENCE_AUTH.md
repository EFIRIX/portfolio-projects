# CODE REFERENCE - Production Auth System

## 1. Backend Security Modules

### app/core/security.py (Key Functions Added)

```python
# Token types
REFRESH_TOKEN_TYPE = "refresh"

# Generate refresh token
def create_refresh_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a refresh token with longer expiration"""
    token_expiry = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    return create_token(
        subject=subject,
        token_type=REFRESH_TOKEN_TYPE,
        expires_delta=token_expiry,
    )

# Decode refresh token
def decode_refresh_token(token: str) -> Optional[Tuple[str, str]]:  # (user_id, jti)
    """Decode refresh token and return user_id and jti"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None

    if payload.get("type") != REFRESH_TOKEN_TYPE:
        return None

    subject = payload.get("sub")
    jti = payload.get("jti")
    
    if not subject or not jti:
        return None
    
    return str(subject), jti

# Decode with full payload
def decode_token_with_payload(token: str) -> Optional[dict]:
    """Decode token and return full payload"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

### app/core/rate_limit.py (Complete)

```python
class RateLimiter:
    """In-memory rate limiter with sliding window"""

    def __init__(self, max_attempts: int = 5, window_minutes: int = 1):
        self.max_attempts = max_attempts
        self.window_seconds = window_minutes * 60
        self.attempts: Dict[str, List[Tuple[float, int]]] = defaultdict(list)

    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed"""
        if not settings.rate_limit_enabled:
            return True

        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - self.window_seconds

        # Remove old attempts
        self.attempts[identifier] = [
            (ts, count) for ts, count in self.attempts[identifier]
            if ts > cutoff
        ]

        # Count total
        total = sum(count for _, count in self.attempts[identifier])

        if total >= self.max_attempts:
            return False

        # Record attempt
        if self.attempts[identifier] and self.attempts[identifier][-1][0] == now:
            self.attempts[identifier][-1] = (now, self.attempts[identifier][-1][1] + 1)
        else:
            self.attempts[identifier].append((now, 1))

        return True

# Global instance
login_limiter = RateLimiter(
    max_attempts=settings.rate_limit_login_attempts,
    window_minutes=settings.rate_limit_window_minutes
)

def check_rate_limit(identifier: str, limiter: RateLimiter = login_limiter) -> bool:
    return limiter.is_allowed(identifier)
```

### app/core/csrf.py (Complete)

```python
class CSRFManager:
    """Manage CSRF token generation and validation"""

    @staticmethod
    def generate_token() -> str:
        """Generate a new CSRF token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    def validate_token(cookie_token: str, header_token: str) -> bool:
        """
        Validate CSRF token using double-submit cookie pattern.
        Same token must appear in cookie and request header.
        """
        if not settings.csrf_enabled:
            return True
        
        if not cookie_token or not header_token:
            return False
        
        return cookie_token == header_token
```

---

## 2. Token Denylist Model

### app/models/token_denylist.py

```python
class TokenDenylist(Base):
    """Stores invalidated tokens (revoked refresh tokens, etc.)"""
    __tablename__ = "token_denylist"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone.True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
```

---

## 3. Token Service

### app/services/token_service.py

```python
async def revoke_token(
    db: Session,
    jti: str,
    user_id: int,
    token_type: str,
    expires_at: datetime,
) -> TokenDenylist:
    """Add token to denylist"""
    token_entry = TokenDenylist(
        jti=jti,
        user_id=user_id,
        token_type=token_type,
        expires_at=expires_at,
    )
    db.add(token_entry)
    db.commit()
    db.refresh(token_entry)
    return token_entry

async def is_token_revoked(db: Session, jti: str) -> bool:
    """Check if token is in denylist"""
    return db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first() is not None
```

---

## 4. Auth Endpoints (Key Functions)

### app/api/v1/endpoints/auth.py (Highlights)

```python
# CSRF token endpoint
@router.get("/csrf-token", response_model=CSRFTokenResponse)
def get_csrf_token(response: Response) -> CSRFTokenResponse:
    """Get CSRF token"""
    csrf_token = CSRFManager.generate_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,  # Must be readable
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=3600,
        path="/",
    )
    return CSRFTokenResponse(csrf_token=csrf_token)

# Login with rate limiting
@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    identifier = _auth_identifier(payload)
    
    # Rate limit check
    if not check_rate_limit(identifier.lower(), login_limiter):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа",
        )
    
    # ... auth logic ...
    
    # Generate tokens
    access_token = create_access_token(str(user.id), timedelta(minutes=settings.access_token_expire_minutes))
    refresh_token = create_refresh_token(str(user.id), timedelta(days=settings.refresh_token_expire_days))
    csrf_token = CSRFManager.generate_token()
    
    _set_auth_cookies(response, access_token, refresh_token, csrf_token)
    return AuthResponse(message="Вход выполнен", user=UserOut.model_validate(user))

# Refresh token endpoint
@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_access_token(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    refresh_token: Optional[str] = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    decoded = decode_refresh_token(refresh_token)
    if not decoded:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user_id, jti = decoded

    # Check if revoked
    if db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен отозван")

    # Generate new access token
    new_access_token = create_access_token(str(user_id), timedelta(minutes=settings.access_token_expire_minutes))

    response.set_cookie(
        key=settings.cookie_name,
        value=new_access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    return RefreshTokenResponse(message="Токен обновлён")

# Logout with token revocation
@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=settings.cookie_name),
    refresh_token: Optional[str] = Cookie(default=None, alias=settings.refresh_cookie_name),
):
    # Revoke access token
    if access_token:
        payload = decode_token_with_payload(access_token)
        if payload and payload.get("sub"):
            await revoke_token(db, payload["jti"], int(payload["sub"]), "access", datetime.fromtimestamp(payload["exp"]))

    # Revoke refresh token
    if refresh_token:
        payload = decode_token_with_payload(refresh_token)
        if payload and payload.get("sub"):
            await revoke_token(db, payload["jti"], int(payload["sub"]), "refresh", datetime.fromtimestamp(payload["exp"]))

    # Clear cookies
    response.delete_cookie(key=settings.cookie_name, path="/")
    response.delete_cookie(key=settings.refresh_cookie_name, path="/api/v1/auth")
    response.delete_cookie(key=settings.csrf_cookie_name, path="/")

    return LogoutResponse(message="Вы вышли из аккаунта")
```

---

## 5. Updated Dependencies

### app/api/deps.py (get_current_user)

```python
def get_current_user(
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=settings.cookie_name),
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Check if token is revoked
    payload = decode_token_with_payload(access_token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    
    jti = payload.get("jti")
    if jti and db.query(TokenDenylist).filter(TokenDenylist.jti == jti).first():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен отозван")

    user_id = decode_access_token(access_token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user
```

---

## 6. Configuration

### app/core/config.py (New Settings)

```python
# Token expiration
access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
reset_token_expire_minutes: int = Field(default=15, alias="RESET_TOKEN_EXPIRE_MINUTES")

# Rate limiting
rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
rate_limit_login_attempts: int = Field(default=5, alias="RATE_LIMIT_LOGIN_ATTEMPTS")
rate_limit_window_minutes: int = Field(default=1, alias="RATE_LIMIT_WINDOW_MINUTES")

# CSRF
csrf_enabled: bool = Field(default=True, alias="CSRF_ENABLED")

# Cookies
cookie_name: str = Field(default="access_token", alias="COOKIE_NAME")
refresh_cookie_name: str = Field(default="refresh_token", alias="REFRESH_COOKIE_NAME")
csrf_cookie_name: str = Field(default="csrf_token", alias="CSRF_COOKIE_NAME")

# Note: SECRET_KEY now required (no fallback)
secret_key: str = Field(alias="SECRET_KEY")  # Required!
```

---

## 7. Schemas

### app/schemas/auth.py (New Schemas)

```python
class RefreshTokenRequest(BaseModel):
    """Request to refresh access token"""
    pass  # Token comes from cookie

class RefreshTokenResponse(BaseModel):
    """Response with new access token"""
    message: str
    access_token: Optional[str] = None  # For API responses

class CSRFTokenResponse(BaseModel):
    """Response with CSRF token"""
    csrf_token: str

class LogoutResponse(BaseModel):
    """Response after logout"""
    message: str
```

---

## Summary of Changes

**New Files:**
- `app/core/rate_limit.py`
- `app/core/csrf.py`
- `app/models/token_denylist.py`
- `app/services/token_service.py`

**Modified Files:**
- `app/core/security.py` - Added refresh token functions
- `app/core/config.py` - Added new settings
- `app/api/deps.py` - Added token revocation check
- `app/api/v1/endpoints/auth.py` - Completely rewritten with new endpoints
- `app/schemas/auth.py` - Added new response schemas

**Database:**
- `alembic/versions/0008_add_token_denylist.py` - New migration

**Configuration:**
- `SECRET_KEY` now required (no default)
- New settings for token expiration, rate limiting, CSRF
