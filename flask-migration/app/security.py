"""Bcrypt-compatible passwords and independent JWT verification."""
from datetime import datetime, timedelta, timezone
from functools import wraps
from threading import Lock
import re
import bcrypt
import jwt
from flask import current_app, g, jsonify, request, session
from sqlalchemy import select
from .models import User

COMMON = {'password', '12345678', '123456789', 'qwerty123', 'password1',
          '11111111', 'abc12345', 'dailywork', 'letmein1', 'admin123'}


def password_error(pwd, email='', name=''):
    if not pwd or not pwd.strip(): return 'Please enter a password.'
    if len(pwd) < 8: return 'Password must be at least 8 characters long.'
    if len(pwd) > 128: return 'Password must be shorter than 128 characters.'
    if not any(c.isalpha() for c in pwd): return 'Password must contain at least one letter.'
    if not any(c.isdigit() for c in pwd): return 'Password must contain at least one number.'
    if pwd.lower() in COMMON: return 'That password is too easy to guess. Please choose another one.'
    local=email.split('@')[0]
    if len(local)>=4 and local.lower() in pwd.lower(): return 'Password must not contain your email address.'
    if len(name.strip())>=4 and name.strip().lower() in pwd.lower(): return 'Password must not contain your name.'
    return None


def new_hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('ascii')


def check_hash(password, hashed):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('ascii'))
    except (ValueError, UnicodeError):
        return False


def stamp_text(user):
    # Native .NET token stamp ticks have 100-ns precision and are not reused.
    # New Flask JWTs use the migrated timestamp as a stable equality check.
    return user.security_stamp.isoformat(timespec='microseconds')


def token_for(user):
    now=datetime.now(timezone.utc)
    claims={'sub':str(user.id),'role':user.role,'stamp':stamp_text(user),
            'iss':current_app.config['JWT_ISSUER'],'aud':current_app.config['JWT_AUDIENCE'],
            'iat':now,'exp':now+timedelta(hours=12)}
    return jwt.encode(claims, current_app.config['JWT_SECRET'], algorithm='HS256')


def current_user():
    cached=getattr(g, '_user_checked', False)
    if cached:
        return getattr(g, '_current_user', None)
    g._user_checked=True
    auth=request.headers.get('Authorization','')
    if not auth.startswith('Bearer '):
        uid=session.get('uid')
        user=g.db.get(User,uid) if isinstance(uid,int) else None
        if not user or not user.is_active or stamp_text(user)!=session.get('stamp'):
            user=None
        g._current_user=user
        return user
    try:
        claims=jwt.decode(auth[7:], current_app.config['JWT_SECRET'],
                          algorithms=['HS256'], issuer=current_app.config['JWT_ISSUER'],
                          audience=current_app.config['JWT_AUDIENCE'], leeway=60)
        user=g.db.get(User, int(claims['sub']))
        if not user or not user.is_active or user.role != claims.get('role') or stamp_text(user) != claims.get('stamp'):
            user=None
    except (jwt.PyJWTError, ValueError, KeyError):
        user=None
    g._current_user=user
    return user


def require_roles(*roles):
    def decorate(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            user=current_user()
            if not user:
                return jsonify(message='Authentication required.'),401
            if roles and user.role not in roles:
                return jsonify(message='Forbidden.'),403
            return handler(*args, **kwargs)
        return wrapped
    return decorate


def require_owner(job, user):
    return job.employer_id == user.id or user.role == 'admin'


# Single-process lockout matching the existing LoginThrottle.
# For multi-worker deployment, replace with a shared Redis-backed limiter.
_LOGIN_LOCK = Lock()
_FAILURES = {}

def login_wait(email, ip):
    from time import monotonic
    key=(email,ip or 'unknown')
    with _LOGIN_LOCK:
        entry=_FAILURES.get(key)
        if not entry:return 0
        first,failures,until=entry
        if until>monotonic():return int(until-monotonic())+1
        if monotonic()-first>900 or until:
            _FAILURES.pop(key,None)
        return 0

def login_failure(email,ip):
    from time import monotonic
    key=(email,ip or 'unknown');t=monotonic()
    with _LOGIN_LOCK:
        first,failures,until=_FAILURES.get(key,(t,0,0))
        if t-first>900:first,failures=t,0
        failures+=1
        _FAILURES[key]=(first,failures,t+900 if failures>=5 else 0)

def login_success(email,ip):
    with _LOGIN_LOCK:_FAILURES.pop((email,ip or 'unknown'),None)
