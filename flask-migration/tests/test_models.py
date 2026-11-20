from decimal import Decimal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models import Base, User, Job, JobApplication, Payment, Scaled100


def test_12_tables_and_153_columns():
    assert len(Base.metadata.tables)==12
    assert sum(len(x.columns) for x in Base.metadata.tables.values())==153


def test_round_trip_money_cents_and_units():
    e=create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(e)
    with Session(e) as s:
        u=User(name='Test',email='test@example.com',phone='077',password_hash='$2b$',
               role='employer',experience_years=0)
        s.add(u);s.flush()
        j=Job(title='Harvest',category='Farming',location='Galle',district='Galle',description='',
          pay=Decimal('2500.12'),per='day',urgent=False,workers_needed=1,expected_units=2,
          employer_id=u.id)
        s.add(j);s.flush()
        p=Payment(job_id=j.id,worker_id=u.id,agreed_rate=Decimal('2500.12'),
           units_worked=Decimal('1.25'),amount=Decimal('3125.15'),amount_paid=Decimal('1000.05'),
           confirmed_amount=Decimal('200.00'),worker_confirmed=False,status='partial')
        s.add(p);s.commit()
        fetched=s.get(Payment,p.id)
        assert fetched.amount == Decimal('3125.15')
        assert fetched.units_worked == Decimal('1.25')
        assert fetched.outstanding == Decimal('2125.10')
        assert fetched.awaiting_confirmation == Decimal('800.05')
        raw=s.connection().exec_driver_sql('SELECT Amount FROM Payments').scalar()
        assert raw==312515


def test_round_half_away_from_zero():
    typ=Scaled100()
    assert typ.process_bind_param(Decimal('1.005'),None)==101
    assert typ.process_bind_param(Decimal('-1.005'),None)==-101


def test_unique_application_per_worker_job():
    assert any(idx.unique and {c.name for c in idx.columns}=={'JobId','WorkerId'}
               for idx in Base.metadata.tables['Applications'].indexes)
