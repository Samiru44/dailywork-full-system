"""First-pass port of JobsController, with familiar API field names."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, func, or_, desc, asc
from ..models import Job, User, JobApplication, Project
from ..security import current_user, require_roles, require_owner
from ..serialize import job_dto

bp=Blueprint('jobs',__name__,url_prefix='/api/jobs')


def read_int(value, default):
    try:return int(value)
    except (ValueError, TypeError): return default


def parse_job(d):
    title=str(d.get('title') or '').strip()
    category=str(d.get('category') or '').strip()
    location=str(d.get('location') or '').strip()
    if not title or not category or not location: raise ValueError('Title, category and location are required.')
    if len(title)>191 or len(category)>191: raise ValueError('Title or category is too long.')
    try: pay=Decimal(str(d.get('pay',0))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    except (InvalidOperation,ValueError): raise ValueError('Invalid wage amount.')
    if not pay.is_finite() or pay<0 or pay>1000000: raise ValueError('Pay must be between 0 and 1,000,000.')
    per=(str(d.get('per') or 'day')).strip().lower()
    if per not in ('day','shift','hour'): raise ValueError('Pay unit must be day, shift or hour.')
    def date_val(k):
        v=d.get(k)
        if not v:return None
        try:return datetime.fromisoformat(v.replace('Z','+00:00')).replace(tzinfo=None)
        except (TypeError,ValueError):raise ValueError(f'Invalid {k}.')
    workers=read_int(d.get('workersNeeded'),1)
    units=read_int(d.get('expectedUnits'),1)
    start=date_val('startDate');end=date_val('endDate')
    if start and end and end < start: raise ValueError('End date cannot be before start date.')
    return dict(title=title,category=category,location=location,
      district=str(d.get('district') or location).strip(),description=str(d.get('description') or '').strip(),
      required_skills=str(d.get('requiredSkills') or '').strip(),pay=pay,per=per,
      urgent=bool(d.get('urgent',False)),workers_needed=max(1,workers),expected_units=max(1,units),
      start_date=start,end_date=end)


def related(jobs):
    if not jobs:return {},{}
    ids=[j.id for j in jobs]
    emps={x.id:x for x in g.db.scalars(select(User).where(User.id.in_([j.employer_id for j in jobs])))}
    apps={x:[] for x in ids}
    for a in g.db.scalars(select(JobApplication).where(JobApplication.job_id.in_(ids))):apps[a.job_id].append(a)
    return emps,apps


@bp.get('')
def list_jobs():
    q=request.args
    try:
        minpay=Decimal(q['minPay']) if q.get('minPay') else None
        maxpay=Decimal(q['maxPay']) if q.get('maxPay') else None
    except InvalidOperation:return jsonify(message='Invalid wage range.'),400
    if (minpay is not None and (not minpay.is_finite() or minpay<0)) or (maxpay is not None and (not maxpay.is_finite() or maxpay<0)):
        return jsonify(message='Wage limits cannot be negative.'),400
    if minpay is not None and maxpay is not None and minpay>maxpay:
        return jsonify(message='The minimum wage cannot be higher than the maximum.'),400
    page=max(read_int(q.get('page'),1),1)
    size=read_int(q.get('pageSize'),20)
    size=size if 1<=size<=100 else 20
    sort=q.get('sort','relevance').lower()
    if sort not in ('relevance','newest','wage_high','wage_low'):sort='relevance'
    stmt=select(Job).join(User,Job.employer_id==User.id).where(Job.status=='open')
    if q.get('search'):
        pat=f"%{q['search'].strip()}%"
        stmt=stmt.where(or_(Job.title.ilike(pat),Job.category.ilike(pat),Job.description.ilike(pat),
                            Job.required_skills.ilike(pat),User.name.ilike(pat)))
    if q.get('category'):stmt=stmt.where(Job.category==q['category'].strip())
    if q.get('district'):stmt=stmt.where(func.lower(Job.district)==q['district'].strip().lower())
    if q.get('location'):stmt=stmt.where(Job.location.ilike(f"%{q['location'].strip()}%"))
    if minpay is not None:stmt=stmt.where(Job.pay>=minpay)
    if maxpay is not None:stmt=stmt.where(Job.pay<=maxpay)
    if q.get('urgentOnly','').lower()=='true':stmt=stmt.where(Job.urgent.is_(True))
    if q.get('verifiedOnly','').lower()=='true':stmt=stmt.where(User.verification_status=='verified')
    import re
    for skill in [x.strip() for x in re.split('[,;]',q.get('skills','')) if len(x.strip())>1]:
        pat=f'%{skill}%'
        stmt=stmt.where(or_(Job.required_skills.ilike(pat),Job.title.ilike(pat),Job.category.ilike(pat)))
    stmt=stmt.order_by(Job.pay.desc(),Job.created_at.desc()) if sort=='wage_high' else (
         stmt.order_by(Job.pay.asc(),Job.created_at.desc()) if sort=='wage_low' else (
         stmt.order_by(Job.created_at.desc()) if sort=='newest' else
         stmt.order_by(Job.urgent.desc(),Job.created_at.desc())))
    # Source controller materializes before availableOnly filter; maintain same pagination semantics.
    jobs=list(g.db.scalars(stmt)); emps,apps=related(jobs)
    if q.get('availableOnly','').lower()=='true':
        jobs=[j for j in jobs if sum(a.status in ('accepted','completed') for a in apps[j.id])<j.workers_needed]
    total=len(jobs)
    return jsonify(total=total,page=page,pageSize=size,totalPages=(total+size-1)//size,sort=sort,
                   jobs=[job_dto(j,emps.get(j.employer_id),apps.get(j.id,[])) for j in jobs[(page-1)*size:page*size]])


@bp.get('/<int:id>')
def details(id):
    j=g.db.get(Job,id)
    if not j:return jsonify(message='Job not found.'),404
    emps,apps=related([j]);e=emps.get(j.employer_id)
    from ..models import Rating
    ratings=list(g.db.scalars(select(Rating.stars).where(Rating.subject_id==j.employer_id)))
    me=current_user()
    already=bool(me and g.db.scalar(select(JobApplication.id).where(JobApplication.job_id==id,JobApplication.worker_id==me.id)))
    return jsonify(job=job_dto(j,e,apps.get(j.id,[])),alreadyApplied=already,employer={
      'id':j.employer_id,'name':e.name if e else '', 'verified':e.is_verified if e else False,
      'organizationName':e.organization_name if e else '',
      'location':e.location if e else '', 'memberSince':e.created_at.isoformat() if e and e.created_at else None,
      'jobsPosted':g.db.scalar(select(func.count()).select_from(Job).where(Job.employer_id==j.employer_id)),
      'rating':round(sum(ratings)/len(ratings),1) if ratings else 0,'ratingCount':len(ratings)})


@bp.post('')
@require_roles('employer','organization','admin')
def create():
    d=request.get_json(silent=True) or {}
    try: values=parse_job(d)
    except ValueError as exc:return jsonify(message=str(exc)),400
    me=current_user()
    project_id=d.get('projectId') or None
    if project_id:
        p=g.db.get(Project,read_int(project_id,0))
        if not p or (p.organization_id!=me.id and me.role!='admin'):
            return jsonify(message='Invalid project.'),400
        project_id=p.id
    j=Job(**values,employer_id=me.id,project_id=project_id,status='open')
    g.db.add(j);g.db.commit()
    # Email and recommendation notifications are NOT yet ported.
    return jsonify(id=j.id,message='Job posted.'),201


@bp.put('/<int:id>')
@require_roles('employer','organization','admin')
def update(id):
    j=g.db.get(Job,id);me=current_user()
    if not j:return jsonify(message='Job not found.'),404
    if not require_owner(j,me):return jsonify(message='Forbidden.'),403
    d=request.get_json(silent=True) or {}
    try:values=parse_job(d)
    except ValueError as exc:return jsonify(message=str(exc)),400
    for key,val in values.items():setattr(j,key,val)
    j.updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
    g.db.commit();return jsonify(message='Job updated.')


@bp.delete('/<int:id>')
@require_roles('employer','organization','admin')
def close(id):
    j=g.db.get(Job,id);me=current_user()
    if not j:return jsonify(message='Job not found.'),404
    if not require_owner(j,me):return jsonify(message='Forbidden.'),403
    j.status='closed';j.updated_at=datetime.now(timezone.utc).replace(tzinfo=None)
    g.db.commit();return jsonify(message='Job closed.')
