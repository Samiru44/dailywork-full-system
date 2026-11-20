"""SQLAlchemy representation of DailyWork's 12 EF Core DbSets.

IMPORTANT: Original EF ValueConverter stores money and work units as integers
scaled by 100. Python attributes expose Decimal values; MySQL columns remain BIGINT.
Column and table names preserve the exact EF naming used in source data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import re

from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT, DATETIME as MYSQL_DATETIME

LONG_TEXT = Text().with_variant(LONGTEXT(), 'mysql')
LARGE_BLOB = LargeBinary().with_variant(LONGBLOB(), 'mysql')
DB_DATETIME = DateTime().with_variant(MYSQL_DATETIME(fsp=6), 'mysql')
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Scaled100(TypeDecorator):
    '''Preserve EF Core decimal-to-integer ValueConverter; ROUND_HALF_UP for .NET AwayFromZero.'''
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        dec = Decimal(str(value))
        if not dec.is_finite():
            raise ValueError("Money/units must be finite")
        return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value) / Decimal(100)


class Base(DeclarativeBase):
    pass


def snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

class JobApplication(Base):
    __tablename__ = "Applications"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column("JobId", Integer, ForeignKey("Jobs.Id", ondelete="CASCADE"), nullable=False, default=0)
    worker_id: Mapped[int] = mapped_column("WorkerId", Integer, ForeignKey("Users.Id", ondelete="RESTRICT"), nullable=False, default=0)
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="pending")
    message: Mapped[str] = mapped_column("Message", LONG_TEXT, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    shortlisted_at: Mapped[datetime | None] = mapped_column("ShortlistedAt", DB_DATETIME, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column("AcceptedAt", DB_DATETIME, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column("RejectedAt", DB_DATETIME, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column("CompletedAt", DB_DATETIME, nullable=True)
    __table_args__ = (Index("ix_applications_jobid_workerid", "JobId", "WorkerId", unique=True),)

class Project(Base):
    __tablename__ = "Projects"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column("OrganizationId", Integer, ForeignKey("Users.Id", ondelete="CASCADE"), nullable=False, default=0)
    name: Mapped[str] = mapped_column("Name", String(191), nullable=False, default="")
    description: Mapped[str] = mapped_column("Description", LONG_TEXT, nullable=False, default="")
    location: Mapped[str] = mapped_column("Location", LONG_TEXT, nullable=False, default="")
    district: Mapped[str] = mapped_column("District", LONG_TEXT, nullable=False, default="")
    workers_required: Mapped[int] = mapped_column("WorkersRequired", Integer, nullable=False, default=0)
    budget: Mapped[Decimal] = mapped_column("Budget", Scaled100, nullable=False, default=0)
    start_date: Mapped[datetime | None] = mapped_column("StartDate", DB_DATETIME, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column("EndDate", DB_DATETIME, nullable=True)
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="planning")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column("UpdatedAt", DB_DATETIME, nullable=True)
    __table_args__ = (Index("ix_projects_organizationid", "OrganizationId", unique=False),)

class Rating(Base):
    __tablename__ = "Ratings"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column("JobId", Integer, ForeignKey("Jobs.Id", ondelete="CASCADE"), nullable=False, default=0)
    author_id: Mapped[int] = mapped_column("AuthorId", Integer, ForeignKey("Users.Id", ondelete="RESTRICT"), nullable=False, default=0)
    subject_id: Mapped[int] = mapped_column("SubjectId", Integer, ForeignKey("Users.Id", ondelete="RESTRICT"), nullable=False, default=0)
    stars: Mapped[int] = mapped_column("Stars", Integer, nullable=False, default=0)
    comment: Mapped[str] = mapped_column("Comment", LONG_TEXT, nullable=False, default="")
    subject_role: Mapped[str] = mapped_column("SubjectRole", LONG_TEXT, nullable=False, default="worker")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_ratings_jobid_authorid", "JobId", "AuthorId", unique=True),)

class PaymentAudit(Base):
    __tablename__ = "PaymentAudits"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column("PaymentId", Integer, ForeignKey("Payments.Id", ondelete="CASCADE"), nullable=False, default=0)
    action: Mapped[str] = mapped_column("Action", LONG_TEXT, nullable=False, default="")
    from_status: Mapped[str] = mapped_column("FromStatus", LONG_TEXT, nullable=False, default="")
    to_status: Mapped[str] = mapped_column("ToStatus", LONG_TEXT, nullable=False, default="")
    amount_at_change: Mapped[Decimal] = mapped_column("AmountAtChange", Scaled100, nullable=False, default=0)
    actor_user_id: Mapped[int] = mapped_column("ActorUserId", Integer, nullable=False, default=0)
    actor_role: Mapped[str] = mapped_column("ActorRole", LONG_TEXT, nullable=False, default="")
    note: Mapped[str] = mapped_column("Note", LONG_TEXT, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)

class JobCategory(Base):
    __tablename__ = "JobCategories"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("Name", String(191), nullable=False, default="")
    description: Mapped[str] = mapped_column("Description", LONG_TEXT, nullable=False, default="")
    icon: Mapped[str] = mapped_column("Icon", LONG_TEXT, nullable=False, default="fa-briefcase")
    sort_order: Mapped[int] = mapped_column("SortOrder", Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column("IsActive", Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_jobcategories_name", "Name", unique=True),)

class User(Base):
    __tablename__ = "Users"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("Name", String(191), nullable=False, default="")
    email: Mapped[str] = mapped_column("Email", String(254), nullable=False, default="")
    phone: Mapped[str] = mapped_column("Phone", LONG_TEXT, nullable=False, default="")
    password_hash: Mapped[str] = mapped_column("PasswordHash", LONG_TEXT, nullable=False, default="")
    role: Mapped[str] = mapped_column("Role", String(64), nullable=False, default="worker")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    is_active: Mapped[bool] = mapped_column("IsActive", Boolean, nullable=False, default=True)
    deactivated_at: Mapped[datetime | None] = mapped_column("DeactivatedAt", DB_DATETIME, nullable=True)
    deactivation_reason: Mapped[str] = mapped_column("DeactivationReason", LONG_TEXT, nullable=False, default="")
    security_stamp: Mapped[datetime] = mapped_column("SecurityStamp", DB_DATETIME, nullable=False, default=utcnow)
    skills: Mapped[str] = mapped_column("Skills", LONG_TEXT, nullable=False, default="")
    location: Mapped[str] = mapped_column("Location", LONG_TEXT, nullable=False, default="")
    district: Mapped[str] = mapped_column("District", LONG_TEXT, nullable=False, default="")
    bio: Mapped[str] = mapped_column("Bio", LONG_TEXT, nullable=False, default="")
    available: Mapped[bool] = mapped_column("Available", Boolean, nullable=False, default=True)
    experience: Mapped[str] = mapped_column("Experience", LONG_TEXT, nullable=False, default="")
    experience_years: Mapped[int] = mapped_column("ExperienceYears", Integer, nullable=False, default=0)
    certifications: Mapped[str] = mapped_column("Certifications", LONG_TEXT, nullable=False, default="")
    verification_status: Mapped[str] = mapped_column("VerificationStatus", String(64), nullable=False, default="unverified")
    organization_name: Mapped[str] = mapped_column("OrganizationName", LONG_TEXT, nullable=False, default="")
    registration_number: Mapped[str] = mapped_column("RegistrationNumber", LONG_TEXT, nullable=False, default="")
    organization_address: Mapped[str] = mapped_column("OrganizationAddress", LONG_TEXT, nullable=False, default="")
    organization_website: Mapped[str] = mapped_column("OrganizationWebsite", LONG_TEXT, nullable=False, default="")
    verification_notes: Mapped[str] = mapped_column("VerificationNotes", LONG_TEXT, nullable=False, default="")
    verification_decision_note: Mapped[str] = mapped_column("VerificationDecisionNote", LONG_TEXT, nullable=False, default="")
    verification_requested_at: Mapped[datetime | None] = mapped_column("VerificationRequestedAt", DB_DATETIME, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column("VerifiedAt", DB_DATETIME, nullable=True)
    verified_by_user_id: Mapped[int | None] = mapped_column("VerifiedByUserId", Integer, nullable=True)
    __table_args__ = (
        Index("ix_users_email", "Email", unique=True),
        Index("ix_users_role", "Role", unique=False),
        Index("ix_users_verificationstatus", "VerificationStatus", unique=False),
    )
    @property
    def is_verified(self):
        return self.verification_status == "verified"

class Notification(Base):
    __tablename__ = "Notifications"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("UserId", Integer, ForeignKey("Users.Id", ondelete="CASCADE"), nullable=False, default=0)
    title: Mapped[str] = mapped_column("Title", LONG_TEXT, nullable=False, default="")
    message: Mapped[str] = mapped_column("Message", LONG_TEXT, nullable=False, default="")
    type: Mapped[str] = mapped_column("Type", LONG_TEXT, nullable=False, default="system")
    is_read: Mapped[bool] = mapped_column("IsRead", Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_notifications_userid_isread", "UserId", "IsRead", unique=False),)

class ContactMessage(Base):
    __tablename__ = "ContactMessages"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("Name", String(191), nullable=False, default="")
    email: Mapped[str] = mapped_column("Email", String(254), nullable=False, default="")
    subject: Mapped[str] = mapped_column("Subject", LONG_TEXT, nullable=False, default="")
    message: Mapped[str] = mapped_column("Message", LONG_TEXT, nullable=False, default="")
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="new")
    user_id: Mapped[int | None] = mapped_column("UserId", Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column("HandledAt", DB_DATETIME, nullable=True)
    __table_args__ = (Index("ix_contactmessages_status", "Status", unique=False),)

class CvDocument(Base):
    __tablename__ = "CvDocuments"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("UserId", Integer, ForeignKey("Users.Id", ondelete="CASCADE"), nullable=False, default=0)
    file_name: Mapped[str] = mapped_column("FileName", LONG_TEXT, nullable=False, default="")
    content_type: Mapped[str] = mapped_column("ContentType", LONG_TEXT, nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column("SizeBytes", BigInteger, nullable=False, default=0)
    data: Mapped[bytes] = mapped_column("Data", LARGE_BLOB, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column("UploadedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_cvdocuments_userid", "UserId", unique=True),)

class Job(Base):
    __tablename__ = "Jobs"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column("Title", LONG_TEXT, nullable=False, default="")
    category: Mapped[str] = mapped_column("Category", String(191), nullable=False, default="")
    location: Mapped[str] = mapped_column("Location", LONG_TEXT, nullable=False, default="")
    district: Mapped[str] = mapped_column("District", LONG_TEXT, nullable=False, default="")
    description: Mapped[str] = mapped_column("Description", LONG_TEXT, nullable=False, default="")
    pay: Mapped[Decimal] = mapped_column("Pay", Scaled100, nullable=False, default=0)
    per: Mapped[str] = mapped_column("Per", LONG_TEXT, nullable=False, default="day")
    urgent: Mapped[bool] = mapped_column("Urgent", Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="open")
    required_skills: Mapped[str] = mapped_column("RequiredSkills", LONG_TEXT, nullable=False, default="")
    workers_needed: Mapped[int] = mapped_column("WorkersNeeded", Integer, nullable=False, default=1)
    expected_units: Mapped[int] = mapped_column("ExpectedUnits", Integer, nullable=False, default=1)
    start_date: Mapped[datetime | None] = mapped_column("StartDate", DB_DATETIME, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column("EndDate", DB_DATETIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column("UpdatedAt", DB_DATETIME, nullable=True)
    employer_id: Mapped[int] = mapped_column("EmployerId", Integer, ForeignKey("Users.Id", ondelete="CASCADE"), nullable=False, default=0)
    project_id: Mapped[int | None] = mapped_column("ProjectId", Integer, ForeignKey("Projects.Id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (
        Index("ix_jobs_status", "Status", unique=False),
        Index("ix_jobs_category", "Category", unique=False),
    )

class Payment(Base):
    __tablename__ = "Payments"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column("JobId", Integer, ForeignKey("Jobs.Id", ondelete="CASCADE"), nullable=False, default=0)
    worker_id: Mapped[int] = mapped_column("WorkerId", Integer, ForeignKey("Users.Id", ondelete="RESTRICT"), nullable=False, default=0)
    application_id: Mapped[int | None] = mapped_column("ApplicationId", Integer, ForeignKey("Applications.Id", ondelete="SET NULL"), nullable=True)
    agreed_rate: Mapped[Decimal] = mapped_column("AgreedRate", Scaled100, nullable=False, default=0)
    rate_unit: Mapped[str] = mapped_column("RateUnit", LONG_TEXT, nullable=False, default="day")
    units_worked: Mapped[Decimal] = mapped_column("UnitsWorked", Scaled100, nullable=False, default=1)
    amount: Mapped[Decimal] = mapped_column("Amount", Scaled100, nullable=False, default=0)
    amount_paid: Mapped[Decimal] = mapped_column("AmountPaid", Scaled100, nullable=False, default=0)
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="pending")
    paid_at: Mapped[datetime | None] = mapped_column("PaidAt", DB_DATETIME, nullable=True)
    method: Mapped[str] = mapped_column("Method", LONG_TEXT, nullable=False, default="")
    notes: Mapped[str] = mapped_column("Notes", LONG_TEXT, nullable=False, default="")
    worker_confirmed: Mapped[bool] = mapped_column("WorkerConfirmed", Boolean, nullable=False, default=False)
    confirmed_amount: Mapped[Decimal] = mapped_column("ConfirmedAmount", Scaled100, nullable=False, default=0)
    worker_confirmed_at: Mapped[datetime | None] = mapped_column("WorkerConfirmedAt", DB_DATETIME, nullable=True)
    worker_dispute_note: Mapped[str] = mapped_column("WorkerDisputeNote", LONG_TEXT, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_payments_applicationid", "ApplicationId", unique=True),)
    @property
    def outstanding(self):
        return (self.amount or Decimal(0)) - (self.amount_paid or Decimal(0))

    @property
    def awaiting_confirmation(self):
        return (self.amount_paid or Decimal(0)) - (self.confirmed_amount or Decimal(0))

class WorkRecord(Base):
    __tablename__ = "WorkRecords"
    id: Mapped[int] = mapped_column("Id", Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column("JobId", Integer, ForeignKey("Jobs.Id", ondelete="CASCADE"), nullable=False, default=0)
    worker_id: Mapped[int] = mapped_column("WorkerId", Integer, ForeignKey("Users.Id", ondelete="RESTRICT"), nullable=False, default=0)
    application_id: Mapped[int] = mapped_column("ApplicationId", Integer, ForeignKey("Applications.Id", ondelete="CASCADE"), nullable=False, default=0)
    work_date: Mapped[datetime] = mapped_column("WorkDate", DB_DATETIME, nullable=False)
    units: Mapped[Decimal] = mapped_column("Units", Scaled100, nullable=False, default=1)
    unit: Mapped[str] = mapped_column("Unit", LONG_TEXT, nullable=False, default="day")
    rate_applied: Mapped[Decimal] = mapped_column("RateApplied", Scaled100, nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column("LineTotal", Scaled100, nullable=False, default=0)
    notes: Mapped[str] = mapped_column("Notes", LONG_TEXT, nullable=False, default="")
    verified: Mapped[bool] = mapped_column("Verified", Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column("VerifiedAt", DB_DATETIME, nullable=True)
    status: Mapped[str] = mapped_column("Status", String(64), nullable=False, default="approved")
    submitted_by_user_id: Mapped[int] = mapped_column("SubmittedByUserId", Integer, nullable=False, default=0)
    decision_note: Mapped[str] = mapped_column("DecisionNote", LONG_TEXT, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column("CreatedAt", DB_DATETIME, nullable=False, default=utcnow)
    __table_args__ = (Index("ix_workrecords_applicationid_workdate", "ApplicationId", "WorkDate", unique=False),)
