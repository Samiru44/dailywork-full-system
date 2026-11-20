"""Core job applications, transitions and daily work approvals."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from ..models import (Job, User, JobApplication, WorkRecord, Payment, PaymentAudit, Notification)
from ..security import current_user, require_roles
from ..serialize import application_dto

bp=Blueprint('applications',__name__,url_prefix='/api/applications')
ALLOWED={'pending':{'shortlisted','accepted','rejected'},
         'shortlisted':{'accepted','rejected'},'accepted':{'completed','rejected'},
         'completed':set(),'rejected':set()}

def now():return datetime.now(timezone.utc).replace(tzinfo=None)
def round_money(x):return Decimal(str(x)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def raise_notification(id,typ,title,message):
    g.db.add(Notification(user_id=id,type=typ,title=title,message=message,is_read=False))
def permitted(j,me):return bool(j and (j.employer_id==me.id or me.role=='admin'))
def count_hired(job_id):
    return g.db.scalar(select(func.count()).select_from(JobApplication).where(
      JobApplication.job_id==job_id,JobApplication.status.in_(['accepted','completed']))) or 0


def get_context(id,lock=False):
    a=g.db.get(JobApplication,id,with_for_update=lock)
    return a,(g.db.get(Job,a.job_id) if a else None)


@bp.post('')
@require_roles('worker')
def apply():
    d=request.get_json(silent=True) or {}
    try:jid=int(d.get('jobId',0))
    except (TypeError,ValueError):return jsonify(message='Invalid job.'),400
    # Lock the posting during capacity check and insert.
    j=g.db.get(Job,jid,with_for_update=True)
    if not j:return jsonify(message='Job not found.'),404
    me=current_user()
    if j.status!='open':return jsonify(message='This job is no longer accepting applications.'),400
    if j.end_date and j.end_date.date()<now().date():return jsonify(message='This job has already finished.'),400
    if j.employer_id==me.id:return jsonify(message='You cannot apply to your own job posting.'),400
    old=g.db.scalar(select(JobApplication).where(JobApplication.job_id==jid,JobApplication.worker_id==me.id))
    if old:return jsonify(message='You are already assigned to this job.' if old.status in ('accepted','completed') else 'You have already applied for this job.'),409
    if count_hired(jid)>=j.workers_needed:return jsonify(message='This job has already hired all the workers it needs.'),400
    a=JobApplication(job_id=jid,worker_id=me.id,status='pending',message=str(d.get('message') or '').strip())
    g.db.add(a)
    raise_notification(j.employer_id,'application','New applicant',f'{me.name} applied for "{j.title}".')
    try:g.db.commit()
    except IntegrityError:
        g.db.rollback();return jsonify(message='You have already applied for this job.'),409
    # Sending email and attaching a worker CV is NOT implemented yet.
    return jsonify(message='Application submitted.')


@bp.get('/mine')
@require_roles()
def mine():
    me=current_user()
    apps=list(g.db.scalars(select(JobApplication).where(JobApplication.worker_id==me.id).order_by(JobApplication.created_at.desc())))
    jobs={j.id:j for j in g.db.scalars(select(Job).where(Job.id.in_([a.job_id for a in apps])))} if apps else {}
    emps={u.id:u for u in g.db.scalars(select(User).where(User.id.in_([j.employer_id for j in jobs.values()]))) } if jobs else {}
    return jsonify([application_dto(a,jobs[a.job_id],emps[jobs[a.job_id].employer_id]) for a in apps])


@bp.get('/job/<int:job_id>')
@require_roles('employer','organization','admin')
def applicants(job_id):
    j=g.db.get(Job,job_id)
    if not j:return jsonify(message='Job not found.'),404
    if not permitted(j,current_user()):return jsonify(message='Forbidden.'),403
    apps=list(g.db.scalars(select(JobApplication).where(JobApplication.job_id==job_id)))
    workers={u.id:u for u in g.db.scalars(select(User).where(User.id.in_([a.worker_id for a in apps])))} if apps else {}
    return jsonify([dict(id=a.id,workerName=workers[a.worker_id].name,phone=workers[a.worker_id].phone,
       email=workers[a.worker_id].email,skills=workers[a.worker_id].skills,status=a.status,
       createdAt=a.created_at.isoformat() if a.created_at else None) for a in apps])


def make_payment(a,j,me):
    records=list(g.db.scalars(select(WorkRecord).where(WorkRecord.application_id==a.id,WorkRecord.status=='approved')))
    units=sum((r.units for r in records),Decimal(0)) if records else Decimal(1)
    total=round_money(j.pay*units)
    p=g.db.scalar(select(Payment).where(Payment.application_id==a.id))
    if p:return
    p=Payment(job_id=j.id,worker_id=a.worker_id,application_id=a.id,agreed_rate=j.pay,
              rate_unit=j.per,units_worked=units,amount=total,amount_paid=Decimal(0),status='pending',
              worker_confirmed=False,confirmed_amount=Decimal(0))
    g.db.add(p);g.db.flush()
    g.db.add(PaymentAudit(payment_id=p.id,action='created',from_status='',to_status='pending',
                          amount_at_change=total,actor_user_id=me.id,actor_role=me.role,
                          note='Payment raised after verified work completion.'))


@bp.put('/<int:id>/status')
@require_roles('employer','organization','admin')
def update_status(id):
    d=request.get_json(silent=True) or {}
    target=str(d.get('status') or '').strip().lower()
    if target not in ALLOWED:return jsonify(message='Invalid status.'),400
    a,j=get_context(id,lock=True)
    if not a:return jsonify(message='Application not found.'),404
    me=current_user()
    if not permitted(j,me):return jsonify(message='Forbidden.'),403
    if a.status==target:return jsonify(message=f'This application is already {target}.'),400
    if target not in ALLOWED.get(a.status,set()):return jsonify(message=f'An application cannot move from {a.status} to {target}.'),400
    # Lock posting to serialize competing hires, including separate applications.
    g.db.get(Job,j.id,with_for_update=True)
    if target=='accepted' and count_hired(a.job_id)>=j.workers_needed:
        return jsonify(message='This job has already hired all the workers it needs.'),400
    a.status=target
    for k,status in [('shortlisted_at','shortlisted'),('accepted_at','accepted'),('rejected_at','rejected'),('completed_at','completed')]:
        if status==target:setattr(a,k,now())
    if target=='completed':make_payment(a,j,me)
    raise_notification(a.worker_id,'application','Application updated',f'Your application for "{j.title}" is now {target}.')
    g.db.commit()
    return jsonify(message=f'Application {target}.',status=target)


def update_payment_if_allowed(a,j,me):
    p=g.db.scalar(select(Payment).where(Payment.application_id==a.id).with_for_update())
    if not p:return None
    if p.amount_paid>0:raise ValueError('Payment for this job has already started, so work cannot be changed.')
    rows=list(g.db.scalars(select(WorkRecord).where(WorkRecord.application_id==a.id,WorkRecord.status=='approved')))
    new_units=sum((x.units for x in rows),Decimal(0)) if rows else Decimal(1)
    new_total=round_money(j.pay*new_units)
    before=p.amount
    p.units_worked=new_units;p.amount=new_total
    g.db.add(PaymentAudit(payment_id=p.id,action='adjusted',from_status=p.status,to_status=p.status,
       amount_at_change=new_total,actor_user_id=me.id,actor_role=me.role,
       note=f'Work adjusted; payment changed from {before:.2f} to {new_total:.2f}.'))
    return new_total


@bp.post('/<int:id>/work')
@require_roles()
def submit_work(id):
    a,j=get_context(id,lock=True)
    if not a:return jsonify(message='Application not found.'),404
    me=current_user();employer=permitted(j,me);worker=a.worker_id==me.id
    if not employer and not worker:return jsonify(message='Forbidden.'),403
    if a.status not in ('accepted','completed'):return jsonify(message='The worker must be hired before work is recorded.'),400
    d=request.get_json(silent=True) or {}
    try:units=round_money(Decimal(str(d.get('units',1))))
    except (InvalidOperation,ValueError):return jsonify(message='Invalid units.'),400
    if not units.is_finite() or not Decimal(0)<units<=Decimal(24):return jsonify(message='Units worked must be between 0 and 24.'),400
    try:day=datetime.fromisoformat(str(d.get('workDate') or now().date().isoformat()).replace('Z','+00:00')).replace(tzinfo=None)
    except ValueError:return jsonify(message='Invalid work date.'),400
    day=day.replace(hour=0,minute=0,second=0,microsecond=0)
    if day.date()>now().date():return jsonify(message='Work cannot be recorded for a future date.'),400
    if g.db.scalar(select(WorkRecord.id).where(WorkRecord.application_id==a.id,WorkRecord.work_date==day)):
        return jsonify(message='Work has already been recorded for that date.'),409
    p=g.db.scalar(select(Payment).where(Payment.application_id==a.id).with_for_update())
    if p and p.amount_paid>0:return jsonify(message='Payment has already started; work records cannot be changed.'),400
    r=WorkRecord(job_id=j.id,worker_id=a.worker_id,application_id=a.id,work_date=day,units=units,unit=j.per,
      rate_applied=j.pay,line_total=round_money(j.pay*units),notes=str(d.get('notes') or '').strip(),
      verified=employer,verified_at=now() if employer else None,status='approved' if employer else 'pending',
      submitted_by_user_id=me.id)
    g.db.add(r);g.db.flush()
    new_total=update_payment_if_allowed(a,j,me) if employer else None
    if not employer:raise_notification(j.employer_id,'work','Work day submitted for approval',f'Work submitted for "{j.title}".')
    g.db.commit()
    return jsonify(message='Work recorded.' if employer else 'Submitted for employer approval.',
                  status=r.status,amount=float(new_total) if new_total is not None else None)


@bp.put('/work/<int:record_id>')
@require_roles('employer','organization','admin')
def decide_work(record_id):
    r=g.db.get(WorkRecord,record_id,with_for_update=True)
    if not r:return jsonify(message='Work record not found.'),404
    j=g.db.get(Job,r.job_id);me=current_user()
    if not permitted(j,me):return jsonify(message='Forbidden.'),403
    if r.status!='pending':return jsonify(message='That work record has already been decided.'),400
    a=g.db.get(JobApplication,r.application_id)
    p=g.db.scalar(select(Payment).where(Payment.application_id==a.id).with_for_update())
    if p and p.amount_paid>0:return jsonify(message='Payment has already started; work cannot be changed.'),400
    d=request.get_json(silent=True) or {}
    approve=d.get('approve') is True
    r.status='approved' if approve else 'rejected';r.verified=approve
    r.verified_at=now() if approve else None;r.decision_note=str(d.get('note') or '').strip()
    new_total=update_payment_if_allowed(a,j,me) if approve else None
    raise_notification(a.worker_id,'work','Work record reviewed',f'Your work record for "{j.title}" was {r.status}.')
    g.db.commit()
    return jsonify(message='Work record reviewed.',status=r.status,
                  amount=float(new_total) if new_total is not None else None)


@bp.get('/<int:id>/work')
@require_roles()
def work_records(id):
    a,j=get_context(id)
    if not a:return jsonify(message='Application not found.'),404
    me=current_user()
    if not permitted(j,me) and a.worker_id!=me.id:return jsonify(message='Forbidden.'),403
    rows=list(g.db.scalars(select(WorkRecord).where(WorkRecord.application_id==id).order_by(WorkRecord.work_date)))
    return jsonify([{'id':r.id,'workDate':r.work_date.isoformat(),'units':float(r.units),'unit':r.unit,
      'rateApplied':float(r.rate_applied),'lineTotal':float(r.line_total),'notes':r.notes,
      'verified':r.verified,'status':r.status,'decisionNote':r.decision_note,
      'submittedByWorker':r.submitted_by_user_id==r.worker_id} for r in rows])
