# DEPLOYMENT & TESTING GUIDE

## Part 1: Pre-Deployment Checklist

### Backend Setup

```bash
# 1. Update environment
cat >> .env << EOF
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
RESET_TOKEN_EXPIRE_MINUTES=15
CSRF_ENABLED=true
RATE_LIMIT_ENABLED=true
RATE_LIMIT_LOGIN_ATTEMPTS=5
RATE_LIMIT_WINDOW_MINUTES=1
AUTH_MAX_FAILED_LOGINS=5
AUTH_LOCK_MINUTES=15
COOKIE_SECURE=false  # Set to true in production
COOKIE_SAMESITE=lax
EOF

# 2. Install dependencies (if needed)
pip install -r backend/requirements.txt

# 3. Run migrations
cd backend
alembic upgrade head

# 4. Start backend
python -m uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## Part 2: Manual Testing

### Test 1: Get CSRF Token

```bash
curl -X GET http://localhost:8000/api/v1/auth/csrf-token \
  -H "Content-Type: application/json" \
  -v -c cookies.txt

# Expected:
# HTTP 200
# Response body: {"csrf_token": "..."}
# Response header: set-cookie: csrf_token=...
```

### Test 2: Register User

```bash
CSRF_TOKEN=$(curl -s http://localhost:8000/api/v1/auth/csrf-token | jq -r '.csrf_token')

curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!",
    "full_name": "Test User",
    "login": "testuser"
  }' \
  -c cookies.txt \
  -v

# Expected:
# HTTP 201
# Cookies: access_token, refresh_token, csrf_token
# Response: {message, user}
```

### Test 3: Get Current User

```bash
curl -X GET http://localhost:8000/api/v1/auth/me \
  -b cookies.txt \
  -v

# Expected:
# HTTP 200
# Response: {id, email, login, full_name, ...}
```

### Test 4: Refresh Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -v

# Expected:
# HTTP 200
# New access_token cookie set
# Response: {message: "Токен обновлён"}
```

### Test 5: Rate Limiting (5 failed logins)

```bash
# Try login 6 times with wrong password
for i in {1..6}; do
  echo "Attempt $i:"
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com",
      "password": "WrongPassword123!"
    }' \
    -w "\nHTTP %{http_code}\n\n"
done

# Expected:
# Attempts 1-5: HTTP 401 (invalid password)
# Attempt 6: HTTP 429 (rate limited)
```

### Test 6: Logout (Token Revocation)

```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -b cookies.txt \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -v

# Expected:
# HTTP 200
# Cookies cleared (Set-Cookie with Max-Age=0)
# Response: {message: "Вы вышли из аккаунта"}

# Verify token is revoked
curl -X GET http://localhost:8000/api/v1/auth/me \
  -b cookies.txt

# Expected: HTTP 401 (Токен был отозван)
```

### Test 7: Forgot Password (Dev Mode)

```bash
curl -X POST http://localhost:8000/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com"
  }' \
  -v

# Expected (in dev mode):
# HTTP 200
# Response: {message, reset_token: "..."}
```

### Test 8: Reset Password

```bash
RESET_TOKEN="<token from forgot-password>"

curl -X POST http://localhost:8000/api/v1/auth/reset-password \
  -H "Content-Type: application/json" \
  -d "{
    \"token\": \"$RESET_TOKEN\",
    \"new_password\": \"NewPass456!\"
  }" \
  -v

# Expected:
# HTTP 200
# Response: {message: "Пароль успешно обновлён"}

# Try logging in with new password
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "NewPass456!"
  }' \
  -v

# Expected: HTTP 200 (login success)
```

---

## Part 3: Automated Tests (pytest)

### test_auth_refresh.py

```python
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_refresh_token_valid():
    """Test valid refresh token"""
    # Register
    response = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "TestPass123!",
        "full_name": "Test User"
    })
    assert response.status_code == 201
    
    # Refresh token
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert response.json()["message"] == "Токен обновлён"

def test_refresh_token_revoked():
    """Test revoked refresh token"""
    # Register and logout
    client.post("/api/v1/auth/register", json={...})
    client.post("/api/v1/auth/logout")
    
    # Try to refresh
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401

def test_rate_limiting():
    """Test rate limiting"""
    for i in range(6):
        response = client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPass123!"
        })
        
        if i < 5:
            assert response.status_code == 401
        else:
            assert response.status_code == 429
            assert "Слишком много попыток" in response.json()["detail"]
```

---

## Part 4: Database Query Verification

### Check Token Denylist

```sql
-- Check revoked tokens
SELECT * FROM token_denylist ORDER BY revoked_at DESC;

-- Count tokens per user
SELECT user_id, COUNT(*) as revoked_count 
FROM token_denylist 
GROUP BY user_id;

-- Check expired entries (should be cleaned up)
SELECT COUNT(*) as expired_count 
FROM token_denylist 
WHERE expires_at < NOW();
```

### Cleanup Denylist

```sql
-- Manual cleanup (production: use background task)
DELETE FROM token_denylist 
WHERE expires_at < NOW();
```

---

## Part 5: Production Deployment

### Docker Environment

```yaml
# docker-compose.yml
services:
  backend:
    environment:
      - APP_ENV=production
      - SECRET_KEY=<generated-secure-key>
      - COOKIE_SECURE=true
      - CSRF_ENABLED=true
      - RATE_LIMIT_ENABLED=true
      - LOG_LEVEL=INFO
```

### Nginx Configuration (HTTPS)

```nginx
server {
    listen 443 ssl;
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location /api/v1/auth {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

---

## Part 6: Monitoring

### Health Check Endpoint (Optional)

```python
@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Check system health"""
    try:
        # Test DB connection
        db.execute("SELECT 1")
        
        # Count expired tokens to cleanup
        expired_count = db.query(TokenDenylist).filter(
            TokenDenylist.expires_at < datetime.now(timezone.utc)
        ).count()
        
        return {
            "status": "healthy",
            "database": "connected",
            "expired_tokens_pending_cleanup": expired_count
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }, 500
```

### Logs to Monitor

```
# Info logs
AUTH_LOGIN: user_id=123, ip=192.168.1.1, success=true
AUTH_RATE_LIMIT: identifier=test@example.com, ip=192.168.1.1, attempts=6
AUTH_LOGOUT: user_id=123, tokens_revoked=2
AUTH_TOKEN_REFRESH: user_id=123, success=true

# Error logs
AUTH_INVALID_TOKEN: jti=abc123, reason=revoked
AUTH_CSRF_VALIDATION_FAILED: expected=X, received=Y
```

---

## Part 7: Troubleshooting

### Issue: "Token was revoked" after logout

**Cause:** Token is in denylist  
**Solution:** Check `token_denylist` table, verify cleanup runs

### Issue: Rate limiting too aggressive

**Solution:** Adjust settings
```env
RATE_LIMIT_LOGIN_ATTEMPTS=10  # Increase
RATE_LIMIT_WINDOW_MINUTES=5   # Longer window
```

### Issue: CSRF token mismatch

**Cause:** Cookie not included or header mismatch  
**Solution:** Verify:
1. CSRF endpoint called first
2. Cookie sent in request
3. Header matches cookie value
4. Check `CSRF_ENABLED=true`

### Issue: Refresh token expires immediately

**Cause:** `REFRESH_TOKEN_EXPIRE_DAYS=0`  
**Solution:** Set proper value
```env
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## Part 8: Security Validation

### Checklist

- [ ] SECRET_KEY is secure (32+ random characters)
- [ ] COOKIE_SECURE=true (production only)
- [ ] COOKIE_SAMESITE=lax or strict
- [ ] HTTPS enabled
- [ ] CSRF_ENABLED=true
- [ ] Rate limiting enabled
- [ ] Access token expiration <30 minutes
- [ ] Refresh token expiration 7-30 days
- [ ] Token denylist cleanup running
- [ ] No console logs of tokens/secrets

---

## Next Steps

1. Run manual tests (Part 2)
2. Run automated tests (Part 3)
3. Verify database (Part 4)
4. Deploy to staging
5. Monitor (Part 6)
6. Production deployment
