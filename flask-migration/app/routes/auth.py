"""Matches /api/auth/register and /api/auth/login response fields."""
import re
from flask import Blueprint, jsonify, request, g
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models import User, Notification
from ..security import (password_error,check_hash,new_hash,token_for,
                        login_wait,login_failure,login_success)

bp=Blueprint('auth',__name__,url_prefix='/api/auth')


def response(user):
    return {'id':user.id,'name':user.name,'email':user.email,'role':user.role,
            'verificationStatus':user.verification_status,'token':token_for(user)}


def create_registration(d):
    """Single secure registration service shared by the API and Bootstrap form."""
    name=str(d.get('name') or '').strip()
    email=str(d.get('email') or '').strip().lower()
    phone=str(d.get('phone') or '').strip()
    role=d.get('role')
    pwd=str(d.get('password') or '')
    if role not in ('worker','employer','organization'):
        return None,'Admin accounts cannot be self-registered.',400
    if len(name)<2 or len(name)>191:return None,'Please enter your full name.',400
    if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        return None,'Please enter a valid email address.',400
    count=sum(x.isdigit() for x in phone)
    if not 9<=count<=15:return None,'Please enter a valid phone number.',400
    err=password_error(pwd,email,name)
    if err:return None,err,400
    if g.db.scalar(select(User.id).where(User.email==email)):
        return None,'An account with this email already exists.',409
    user=User(name=name,email=email,phone=phone,role=role,password_hash=new_hash(pwd),
              organization_name=name if role=='organization' else '',experience_years=0)
    g.db.add(user)
    try:
        g.db.flush()
        g.db.add(Notification(user_id=user.id,title='Welcome to DailyWork',type='system',
          message=('Add your skills and location to your profile.' if role=='worker' else
                   'Complete your organization details and request verification.' if role=='organization' else
                   'Post your first job to start receiving applications.'),is_read=False))
        g.db.commit()
    except IntegrityError:
        g.db.rollback()
        return None,'An account with this email already exists.',409
    return user,None,200


@bp.post('/register')
def register():
    user,error,code=create_registration(request.get_json(silent=True) or {})
    return (jsonify(message=error),code) if error else jsonify(response(user))


@bp.post('/login')
def login():
    d=request.get_json(silent=True) or {}
    email=str(d.get('email') or '').strip().lower()
    pwd=str(d.get('password') or '')
    wait=login_wait(email,request.remote_addr)
    if wait:return jsonify(message='Too many failed login attempts. Please try again later.'),429,{'Retry-After':str(wait)}
    user=g.db.scalar(select(User).where(User.email==email))
    if not user or not check_hash(pwd,user.password_hash):
        login_failure(email,request.remote_addr)
        return jsonify(message='Invalid email or password.'),401
    if not user.is_active:
        return jsonify(message='This account has been deactivated. Please contact support.'),401
    login_success(email,request.remote_addr)
    return jsonify(response(user))
