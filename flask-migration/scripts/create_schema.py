"""Create the 12 tables in a new empty MySQL schema. Never alters an existing table."""
import argparse
import os
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.url import make_url
from sqlalchemy.schema import CreateTable, CreateIndex
from app.models import Base

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--apply',action='store_true',help='Execute on a NEW empty MySQL database')
p.add_argument('--url',default=os.environ.get('DATABASE_URL'))
a=p.parse_args()
if not a.url:p.error('DATABASE_URL required')
if not make_url(a.url).drivername.startswith('mysql+'):
    raise SystemExit('Refusing non-MySQL database URL')
engine=create_engine(a.url,pool_pre_ping=True)
if a.apply:
    old=set(inspect(engine).get_table_names())
    if old:raise SystemExit('Refusing non-empty database schema: '+', '.join(sorted(old)))
    Base.metadata.create_all(engine,checkfirst=False)
    print('Created',len(Base.metadata.tables),'new tables. Review constraints and indexes before importing records.')
else:
    for t in Base.metadata.sorted_tables:
        print(str(CreateTable(t).compile(engine)).strip()+';')
        for idx in t.indexes:print(str(CreateIndex(idx).compile(engine)).strip()+';')
    print('\nDRY RUN: no DDL was executed. Use --apply only on a fresh empty schema.')
engine.dispose()
