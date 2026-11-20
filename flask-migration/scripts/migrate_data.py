"""Strict, read-only SQLite -> empty MySQL DailyWork data migration.

- Source database is opened with SQLite mode=ro and never changed.
- Target MUST already have the reviewed SQLAlchemy schema.
- No existing target data is overwritten; failure rolls back all inserts.
- Preserves PKs, FK references, BLOB CV contents, and raw integer cents.
- Performs source/destination row-count and amount/CV checksum checks.

Use a snapshot/backup while the original system is stopped or read-only.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy import create_engine, inspect, select, func, BigInteger, Boolean, DateTime
from sqlalchemy.engine.url import make_url
from app.models import Base, Scaled100


def source_connect(path):
    p=Path(path).resolve(strict=True)
    if not p.is_file():raise ValueError('Source must be a SQLite database file.')
    conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def convert(raw, column):
    if raw is None:return None
    if isinstance(column.type, Scaled100):
        if isinstance(raw,bool) or not isinstance(raw,int):
            raise ValueError(f'Expected raw integer cents for {column.table.name}.{column.name}, got {type(raw).__name__}')
        return Decimal(raw)/Decimal(100)
    if isinstance(column.type, Boolean):return bool(raw)
    if isinstance(column.type, DateTime):
        if isinstance(raw,datetime):return raw.replace(tzinfo=None)
        # .NET's 7th fractional-second digit is truncated to MySQL's 6-digit precision.
        return datetime.fromisoformat(str(raw).replace('Z','+00:00')).replace(tzinfo=None)
    return raw


def hash_rows(rows, table):
    h=hashlib.sha256()
    for row in rows:
        # Preserve binary CV bytes without logging PII; encode stable name:value pairs.
        for col in table.columns:
            val=row[col.name]
            if isinstance(val,memoryview):val=val.tobytes()
            data=bytes(val) if isinstance(val,bytes) else repr(val).encode('utf-8')
            h.update(col.name.encode());h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()


def copy_sqlite_to_engine(src_path,target_url,*,apply=False,allow_sqlite_target=False):
    url=make_url(target_url)
    if not url.drivername.startswith('mysql+') and not (allow_sqlite_target and url.drivername.startswith('sqlite')):
        raise ValueError('Target must be a MySQL SQLAlchemy URL (mysql+pymysql://...).')
    source=source_connect(src_path)
    engine=create_engine(target_url,pool_pre_ping=True)
    ordered=Base.metadata.sorted_tables
    report={}
    try:
        source_tables={x[0] for x in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        dest_tables=set(inspect(engine).get_table_names())
        missing_src=[t.name for t in ordered if t.name not in source_tables]
        missing_dest=[t.name for t in ordered if t.name not in dest_tables]
        if missing_src or missing_dest:
            raise ValueError(f'Missing tables; source={missing_src}, destination={missing_dest}. No changes made.')
        with engine.begin() as dest:
            for table in ordered:
                name=table.name
                source_cols={r[1] for r in source.execute(f'PRAGMA table_info("{name}")')}
                expected_cols={c.name for c in table.columns}
                if source_cols!=expected_cols:
                    raise ValueError(f'{name} source schema mismatch: missing={sorted(expected_cols-source_cols)}, extra={sorted(source_cols-expected_cols)}')
                target_cols={c['name'] for c in inspect(engine).get_columns(name)}
                if target_cols!=expected_cols:
                    raise ValueError(f'{name} target schema mismatch: missing={sorted(expected_cols-target_cols)}, extra={sorted(target_cols-expected_cols)}')
                if dest.scalar(select(func.count()).select_from(table)):
                    raise ValueError(f'{name} destination is not empty. Refusing to overwrite anything.')
            for table in ordered:
                name=table.name
                cur=source.execute(f'SELECT * FROM "{name}" ORDER BY "Id"')
                count=0;amount_sums={c.name:0 for c in table.columns if isinstance(c.type,Scaled100)}
                cv_hash=hashlib.sha256()
                for src in cur:
                    vals={col.name:convert(src[col.name],col) for col in table.columns}
                    for field in amount_sums:amount_sums[field]+=src[field] or 0
                    if name=='CvDocuments':
                        cv_hash.update(int(src['Id']).to_bytes(8,'big'));cv_hash.update(src['Data'] or b'')
                    if apply:dest.execute(table.insert().values(**vals))
                    count+=1
                report[name]={'rows':count,'scaled_integer_totals':amount_sums}
                if name=='CvDocuments':report[name]['blob_sha256']=cv_hash.hexdigest()
                if apply:
                    actual=dest.scalar(select(func.count()).select_from(table))
                    if actual!=count:raise ValueError(f'Count mismatch for {name}: {count} != {actual}')
                    for field,total in amount_sums.items():
                        # SQLAlchemy's scalar of scaled columns returns Decimal; do NOT scale again.
                        col=table.c[field]
                        got=dest.scalar(select(func.sum(col))) or Decimal(0)
                        if got!=Decimal(total)/100:raise ValueError(f'{name}.{field}: amount sum mismatch')
                    if name=='CvDocuments':
                        target_hash=hashlib.sha256()
                        for rid,blob in dest.execute(select(table.c['Id'],table.c['Data']).order_by(table.c['Id'])):
                            target_hash.update(int(rid).to_bytes(8,'big'));target_hash.update(blob or b'')
                        if target_hash.hexdigest()!=cv_hash.hexdigest():raise ValueError('CV content hash mismatch')
            if not apply:
                # Nothing was inserted; transaction still ends safely.
                pass
    finally:
        source.close();engine.dispose()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sqlite',required=True,help='Path to a backed-up SQLite database (read-only)')
    p.add_argument('--target',default=os.environ.get('DATABASE_URL'),help='Empty pre-created MySQL database URL')
    p.add_argument('--apply',action='store_true',help='Actually copy and commit after checks; otherwise dry-run only')
    args=p.parse_args()
    if not args.target:p.error('Set DATABASE_URL or --target')
    report=copy_sqlite_to_engine(args.sqlite,args.target,apply=args.apply)
    print('Copied' if args.apply else 'DRY RUN, NO WRITES')
    for table,data in report.items():print(table,'rows',data['rows'])
    if args.apply:print('Counts, cents totals and CV blob hash verified in destination.')

if __name__=='__main__':main()
