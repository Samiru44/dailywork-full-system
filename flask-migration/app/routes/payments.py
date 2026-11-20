"""Core payment lifecycle, including auditable part payments and confirmations.

Pending independent, live MySQL concurrency testing before production use.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from flask import Blueprint, g, jsonify, request
from sqlalchemy import select
from ..models import Payment, PaymentAudit, Job, User, Notification
from ..security import current_user, require_roles
from ..serialize import payment_dto

bp=Blueprint('payments',__name__,url_prefix='/api/payments')

def now():return datetime.now(timezone.utc).replace(tzinfo=None)
def round_money(x):return Decimal(x).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
def notice(user_id, title, msg):
    g.db.add(Notification(user_id=user_id,title=title,message=msg,type='payment',is_read=False))
def audit(p,user,action,previous,amount,note):
    g.db.add(PaymentAudit(payment_id=p.id,action=action,from_status=previous,to_status=p.status,
        amount_at_change=amount,actor_user_id=user.id,actor_role=user.role,note=note))
def may_view(p,me):
    j=g.db.get(Job,p.job_id)
    return p.worker_id==me.id or (j and j.employer_id==me.id) or me.role=='admin'


@bp.get('/mine')
@require_roles()
def mine():
    me=current_user()
    if me.role=='worker':
        payments=list(g.db.scalars(select(Payment).where(Payment.worker_id==me.id).order_by(Payment.created_at.desc())))
    else:
        payments=list(g.db.scalars(select(Payment).join(Job,Payment.job_id==Job.id).where(Job.employer_id==me.id).order_by(Payment.created_at.desc())))
    jobs={x.id:x for x in g.db.scalars(select(Job).where(Job.id.in_([p.job_id for p in payments])))} if payments else {}
    emps={x.id:x for x in g.db.scalars(select(User).where(User.id.in_([j.employer_id for j in jobs.values()]))) } if jobs else {}
    return jsonify([payment_dto(p,jobs[p.job_id],emps[jobs[p.job_id].employer_id]) for p in payments])


@bp.get('/<int:id>/audit')
@require_roles()
def history(id):
    p=g.db.get(Payment,id)
    if not p:return jsonify(message='Payment not found.'),404
    if not may_view(p,current_user()):return jsonify(message='Forbidden.'),403
    trail=list(g.db.scalars(select(PaymentAudit).where(PaymentAudit.payment_id==id).order_by(PaymentAudit.created_at)))
    return jsonify([{'id':x.id,'action':x.action,'fromStatus':x.from_status,'toStatus':x.to_status,
                     'amountAtChange':float(x.amount_at_change),'actorRole':x.actor_role,
                     'note':x.note,'createdAt':x.created_at.isoformat()} for x in trail])


@bp.put('/<int:id>/pay')
@require_roles('employer','organization','admin')
def pay(id):
    # Explicit row lock ensures concurrent payment requests cannot overpay on MySQL/InnoDB.
    p=g.db.get(Payment,id,with_for_update=True)
    if not p:return jsonify(message='Payment not found.'),404
    me=current_user();j=g.db.get(Job,p.job_id)
    if not j or (j.employer_id != me.id and me.role!='admin'):return jsonify(message='Forbidden.'),403
    if p.status=='paid':return jsonify(message='This payment has already been settled in full and cannot be changed.'),400
    if p.outstanding<=0:return jsonify(message='There is nothing outstanding on this payment.'),400
    d=request.get_json(silent=True) or {}
    try:
        v=d.get('amount')
        amount=round_money(str(v)) if v is not None and Decimal(str(v))>0 else p.outstanding
        if not amount.is_finite():raise InvalidOperation()
    except (InvalidOperation,ValueError,TypeError):return jsonify(message='Invalid payment amount.'),400
    if amount<=0:return jsonify(message='The payment amount must be greater than zero.'),400
    if amount>p.outstanding:return jsonify(message=f'That is more than the outstanding balance of {p.outstanding:.2f}.'),400
    old=p.status; was_confirmed=p.worker_confirmed
    p.amount_paid=round_money(p.amount_paid+amount)
    p.method=str(d.get('method') or p.method or '').strip()
    if d.get('notes'):p.notes=str(d['notes']).strip()
    settled=p.amount_paid>=p.amount
    p.status='paid' if settled else 'partial'
    if settled and not p.paid_at:p.paid_at=now()
    if p.amount_paid>p.confirmed_amount:p.worker_confirmed=False
    audit(p,me,'recorded',old,amount,'Employer recorded final payment.' if settled else 'Employer recorded part payment.')
    notice(p.worker_id,'Payment recorded in full' if settled else 'Part payment recorded',
           f'Rs. {amount:.2f} for "{j.title}" recorded. Please confirm receipt.')
    g.db.commit()
    return jsonify(message='Payment recorded in full.' if settled else 'Part payment recorded.',
      status=p.status,amountPaid=float(p.amount_paid),outstanding=float(p.outstanding),
      workerConfirmed=p.worker_confirmed,awaitingConfirmation=float(p.awaiting_confirmation))


@bp.put('/<int:id>/confirm')
@require_roles('worker')
def confirm(id):
    p=g.db.get(Payment,id,with_for_update=True)
    if not p:return jsonify(message='Payment not found.'),404
    me=current_user()
    if p.worker_id!=me.id:return jsonify(message='Forbidden.'),403
    if p.amount_paid<=0:return jsonify(message='The employer has not recorded any payment yet.'),400
    new=p.awaiting_confirmation
    if new<=0:return jsonify(message='You have already confirmed everything recorded as paid so far.'),400
    p.confirmed_amount=p.amount_paid;p.worker_confirmed=True;p.worker_confirmed_at=now()
    audit(p,me,'confirmed',p.status,new,f'Worker confirmed {new:.2f}.')
    g.db.commit()
    return jsonify(message='Payment receipt confirmed.',workerConfirmed=True,
                  confirmedAmount=float(p.confirmed_amount),outstanding=float(p.outstanding))


@bp.put('/<int:id>/dispute')
@require_roles('worker')
def dispute(id):
    p=g.db.get(Payment,id,with_for_update=True)
    if not p:return jsonify(message='Payment not found.'),404
    me=current_user()
    if p.worker_id!=me.id:return jsonify(message='Forbidden.'),403
    d=request.get_json(silent=True) or {}
    note=str(d.get('note') or d.get('message') or '').strip()
    if not note:return jsonify(message='Please explain the dispute.'),400
    p.worker_dispute_note=note;p.worker_confirmed=False
    audit(p,me,'disputed',p.status,p.awaiting_confirmation,note)
    j=g.db.get(Job,p.job_id)
    if j:notice(j.employer_id,'Payment disputed',f'A payment for "{j.title}" was disputed.')
    g.db.commit()
    return jsonify(message='Payment dispute recorded.')
