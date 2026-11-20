from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.models import Base, User, Job, Payment, CvDocument
from scripts.migrate_data import copy_sqlite_to_engine, source_connect


def prepare(tmp_path):
    src=tmp_path/'original.db'; dst=tmp_path/'converted.db'
    old=create_engine('sqlite+pysqlite:///'+str(src));new=create_engine('sqlite+pysqlite:///'+str(dst))
    Base.metadata.create_all(old);Base.metadata.create_all(new)
    with Session(old) as s:
        e=User(id=3,name='Original',email='old@example.com',phone='077',password_hash='$2a$10$'+('x'*53),
               role='employer',experience_years=0)
        w=User(id=4,name='Worker',email='worker@example.com',phone='077',password_hash='$2a$10$'+('x'*53),
               role='worker',experience_years=3)
        s.add_all([e,w]);s.flush()
        job=Job(id=7,title='Harvest',category='Agriculture',location='Galle',district='Galle',
             description='A test',pay=Decimal('1234.56'),per='day',workers_needed=1,expected_units=2,
             urgent=False,employer_id=3)
        s.add(job)
        cv=CvDocument(user_id=4,file_name='cv.pdf',content_type='application/pdf',
                      size_bytes=8,data=b'%PDF-abc')
        s.add(cv)
        p=Payment(job_id=7,worker_id=4,amount=Decimal('1234.56'),agreed_rate=Decimal('1234.56'),
                  amount_paid=Decimal('10.11'),confirmed_amount=Decimal('10.11'),
                  units_worked=Decimal('1.00'),worker_confirmed=True,status='partial')
        s.add(p);s.commit()
    old.dispose();new.dispose()
    return src,dst


def test_read_only_source(tmp_path):
    src,dst=prepare(tmp_path)
    with source_connect(src) as con:
        with pytest.raises(Exception):con.execute('DELETE FROM Users')


def test_copy_preserves_money_ids_and_cv(tmp_path):
    src,dst=prepare(tmp_path)
    url='sqlite+pysqlite:///'+str(dst)
    report=copy_sqlite_to_engine(src,url,apply=True,allow_sqlite_target=True)
    assert report['Users']['rows']==2
    assert report['Payments']['rows']==1
    assert report['CvDocuments']['rows']==1
    eng=create_engine(url)
    with Session(eng) as s:
        assert s.get(User,4).email=='worker@example.com'
        assert s.get(Job,7).pay==Decimal('1234.56')
        assert s.scalar(select(Payment.amount_paid))==Decimal('10.11')
        assert s.scalar(select(CvDocument.data))==b'%PDF-abc'
    eng.dispose()
    with pytest.raises(ValueError,match='not empty'):
        copy_sqlite_to_engine(src,url,apply=True,allow_sqlite_target=True)


def test_dry_run_does_not_write(tmp_path):
    src,dst=prepare(tmp_path)
    url='sqlite+pysqlite:///'+str(dst)
    copy_sqlite_to_engine(src,url,apply=False,allow_sqlite_target=True)
    eng=create_engine(url)
    with eng.connect() as con:
        assert con.scalar(select(func.count()).select_from(Base.metadata.tables['Users']))==0
    eng.dispose()
