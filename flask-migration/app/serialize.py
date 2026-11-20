"""Camel-case API DTO conversions, keeping legacy React API shape."""
from datetime import datetime, date
from decimal import Decimal
from flask.json.provider import DefaultJSONProvider
from .models import User


def json_decimal(obj):
    if isinstance(obj,Decimal): return float(obj)
    if isinstance(obj,(datetime,date)): return obj.isoformat()
    raise TypeError(type(obj).__name__)


def job_dto(j, employer=None, applications=()):
    apps=list(applications)
    return dict(id=j.id, title=j.title,category=j.category,location=j.location,
      district=j.district,description=j.description,requiredSkills=j.required_skills,
      pay=float(j.pay),per=j.per,urgent=j.urgent,status=j.status,
      workersNeeded=j.workers_needed,expectedUnits=j.expected_units,
      startDate=j.start_date.isoformat() if j.start_date else None,
      endDate=j.end_date.isoformat() if j.end_date else None,
      employerId=j.employer_id,employerName=employer.name if employer else '',
      employerVerified=employer.is_verified if employer else False,
      applications=len(apps), positionsFilled=sum(a.status in ('accepted','completed') for a in apps),
      createdAt=j.created_at.isoformat() if j.created_at else None)


def application_dto(a,j,employer):
    return dict(id=a.id,jobId=a.job_id,jobTitle=j.title,employerName=employer.name,
      location=j.location,pay=float(j.pay),per=j.per,status=a.status,
      createdAt=a.created_at.isoformat() if a.created_at else None,
      acceptedAt=a.accepted_at.isoformat() if a.accepted_at else None,
      completedAt=a.completed_at.isoformat() if a.completed_at else None)


def payment_dto(p,j,employer):
    return dict(id=p.id,jobId=p.job_id,jobTitle=j.title,employerName=employer.name,
     agreedRate=float(p.agreed_rate),rateUnit=p.rate_unit,unitsWorked=float(p.units_worked),
     amount=float(p.amount),amountPaid=float(p.amount_paid),outstanding=float(p.outstanding),
     status=p.status,method=p.method,notes=p.notes,workerConfirmed=p.worker_confirmed,
     confirmedAmount=float(p.confirmed_amount),awaitingConfirmation=float(p.awaiting_confirmation),
     workerConfirmedAt=p.worker_confirmed_at.isoformat() if p.worker_confirmed_at else None,
     workerDisputeNote=p.worker_dispute_note,paidAt=p.paid_at.isoformat() if p.paid_at else None,
     createdAt=p.created_at.isoformat() if p.created_at else None)
