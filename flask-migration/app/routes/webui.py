"""Bootstrap/Jinja2 progressive replacement for the React entry screens.

Additional dashboards and management screens are still to be converted.
"""
from datetime import datetime
import secrets
from flask import (Blueprint, g, redirect, render_template, request, session, url_for, flash)
from sqlalchemy import select
from ..models import Job, User, JobApplication
from ..security import current_user, stamp_text, check_hash, login_wait, login_failure, login_success

bp=Blueprint('webui',__name__)

@bp.before_app_request
def csrf_key():
    if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)

@bp.app_context_processor
def context():
    return {'signed_in_user':current_user(),'csrf_token':session.get('csrf','')}

@bp.get('/')
def home():
    posts=list(g.db.scalars(select(Job).where(Job.status=='open').order_by(Job.created_at.desc()).limit(12)))
    return render_template('index.html',jobs=posts)

@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        email=(request.form.get('email') or '').strip().lower()
        pwd=request.form.get('password') or ''
        wait=login_wait(email,request.remote_addr)
        if wait:
            flash('Too many attempts. Try again later.','danger')
            return render_template('login.html'),429
        user=g.db.scalar(select(User).where(User.email==email))
        if user and user.is_active and check_hash(pwd,user.password_hash):
            login_success(email,request.remote_addr)
            session.clear();session['uid']=user.id;session['stamp']=stamp_text(user)
            session['csrf']=secrets.token_urlsafe(32)
            return redirect(url_for('webui.dashboard'))
        login_failure(email,request.remote_addr)
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@bp.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        from ..routes.auth import create_registration
        user,error,code=create_registration(request.form)
        if error:
            flash(error,'danger')
            return render_template('register.html'),code
        session.clear();session['uid']=user.id;session['stamp']=stamp_text(user)
        session['csrf']=secrets.token_urlsafe(32)
        return redirect(url_for('webui.dashboard'))
    return render_template('register.html')

@bp.post('/logout')
def logout():
    session.clear();return redirect(url_for('webui.home'))

@bp.get('/jobs')
def jobs():
    keyword=request.args.get('search','').strip()
    q=select(Job).where(Job.status=='open')
    if keyword:q=q.where(Job.title.ilike(f'%{keyword}%'))
    posts=list(g.db.scalars(q.order_by(Job.created_at.desc()).limit(50)))
    return render_template('jobs.html',jobs=posts,keyword=keyword)

@bp.get('/jobs/<int:id>')
def job_detail(id):
    job=g.db.get(Job,id)
    if not job:return render_template('error.html',message='Job not found.'),404
    employer=g.db.get(User,job.employer_id)
    user=current_user()
    applied=bool(user and g.db.scalar(select(JobApplication.id).where(JobApplication.job_id==job.id,JobApplication.worker_id==user.id)))
    return render_template('job_detail.html',job=job,employer=employer,applied=applied)

@bp.get('/dashboard')
def dashboard():
    me=current_user()
    if not me:return redirect(url_for('webui.login'))
    if me.role=='worker':
        apps=list(g.db.scalars(select(JobApplication).where(JobApplication.worker_id==me.id).order_by(JobApplication.created_at.desc())))
        jobs={x.id:x for x in g.db.scalars(select(Job).where(Job.id.in_([a.job_id for a in apps])))} if apps else {}
        return render_template('dashboard.html',apps=apps,job_map=jobs,posts=[])
    posts=list(g.db.scalars(select(Job).where(Job.employer_id==me.id).order_by(Job.created_at.desc())))
    return render_template('dashboard.html',apps=[],job_map={},posts=posts)
