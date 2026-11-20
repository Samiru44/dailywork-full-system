"""Deterministic model converter used at bootstrap time. Kept for provenance.

Source: backend/DailyWork.Api/Models/*.cs, AppDbContext.cs from GitHub.
It generates the initial SQLAlchemy declaration; later hand review is required.
"""
import re
from pathlib import Path
src=Path(__file__).resolve().parents[2]/'dailywork-inspection/backend/DailyWork.Api/Models'
files=list(src.glob('*.cs'))
tables={"User":"Users","Job":"Jobs","JobApplication":"Applications","Payment":"Payments","PaymentAudit":"PaymentAudits","WorkRecord":"WorkRecords","Rating":"Ratings","Notification":"Notifications","JobCategory":"JobCategories","ContactMessage":"ContactMessages","Project":"Projects","CvDocument":"CvDocuments"}
# relationship FK, delete; matching AppDbContext.cs
refs={
 ('Job','EmployerId'):('Users','CASCADE'),('Job','ProjectId'):('Projects','SET NULL'),
 ('JobApplication','JobId'):('Jobs','CASCADE'),('JobApplication','WorkerId'):('Users','RESTRICT'),
 ('Payment','JobId'):('Jobs','CASCADE'),('Payment','WorkerId'):('Users','RESTRICT'),('Payment','ApplicationId'):('Applications','SET NULL'),
 ('PaymentAudit','PaymentId'):('Payments','CASCADE'),
 ('WorkRecord','JobId'):('Jobs','CASCADE'),('WorkRecord','WorkerId'):('Users','RESTRICT'),('WorkRecord','ApplicationId'):('Applications','CASCADE'),
 ('Rating','JobId'):('Jobs','CASCADE'),('Rating','AuthorId'):('Users','RESTRICT'),('Rating','SubjectId'):('Users','RESTRICT'),
 ('Notification','UserId'):('Users','CASCADE'),('Project','OrganizationId'):('Users','CASCADE'),('CvDocument','UserId'):('Users','CASCADE')
}
index={"User":[('Email',True),('Role',False),('VerificationStatus',False)],"Job":[('Status',False),('Category',False)],"Project":[('OrganizationId',False)],"JobApplication":[('JobId,WorkerId',True)],"Payment":[('ApplicationId',True)],"WorkRecord":[('ApplicationId,WorkDate',False)],"Rating":[('JobId,AuthorId',True)],"CvDocument":[('UserId',True)],"Notification":[('UserId,IsRead',False)],"JobCategory":[('Name',True)],"ContactMessage":[('Status',False)]}
scaled={('Job','Pay'),('Project','Budget'),('Payment','Amount'),('Payment','AmountPaid'),('Payment','AgreedRate'),('Payment','UnitsWorked'),('Payment','ConfirmedAmount'),('PaymentAudit','AmountAtChange'),('WorkRecord','Units'),('WorkRecord','RateApplied'),('WorkRecord','LineTotal')}
comments='''"""SQLAlchemy representation of DailyWork\'s 12 EF Core DbSets.\n\nIMPORTANT: Original EF ValueConverter stores money and work units as integers\nscaled by 100. Python attributes expose Decimal values; MySQL columns remain BIGINT.\nColumn and table names preserve the exact EF naming used in source data.\n"""\nfrom __future__ import annotations\n\nfrom datetime import datetime, timezone\nfrom decimal import Decimal, ROUND_HALF_UP\nimport re\n\nfrom sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint)\nfrom sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT, DATETIME as MYSQL_DATETIME\n\nLONG_TEXT = Text().with_variant(LONGTEXT(), 'mysql')\nLARGE_BLOB = LargeBinary().with_variant(LONGBLOB(), 'mysql')\nDB_DATETIME = DateTime().with_variant(MYSQL_DATETIME(fsp=6), 'mysql')\nfrom sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\nfrom sqlalchemy.types import TypeDecorator\n\n\ndef utcnow():\n    return datetime.now(timezone.utc).replace(tzinfo=None)\n\n\nclass Scaled100(TypeDecorator):\n    \'\'\'Preserve EF Core decimal-to-integer ValueConverter; ROUND_HALF_UP for .NET AwayFromZero.\'\'\'\n    impl = BigInteger\n    cache_ok = True\n\n    def process_bind_param(self, value, dialect):\n        if value is None:\n            return None\n        dec = Decimal(str(value))\n        if not dec.is_finite():\n            raise ValueError("Money/units must be finite")\n        return int((dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))\n\n    def process_result_value(self, value, dialect):\n        return None if value is None else Decimal(value) / Decimal(100)\n\n\nclass Base(DeclarativeBase):\n    pass\n\n\ndef snake(name):\n    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()\n\n'''
classes=[]
for cs in files:
 c=cs.stem
 s=cs.read_text()
 # only declared auto props (ignore computed props with => )
 props=re.findall(r'public\s+(string\??|int\??|bool\??|long\??|decimal\??|DateTime\??|byte\[\])\s+(\w+)\s*\{\s*get;\s*set;\s*\}(?:\s*=\s*([^;]+);)?',s)
 lines=[f'class {c}(Base):',f'    __tablename__ = "{tables[c]}"']
 for ptype,name,default in props:
  typ=ptype.replace('?','')
  n=re.sub('(?<!^)(?=[A-Z])','_',name).lower()
  nullable=ptype.endswith('?')
  t={'string':'LONG_TEXT','int':'Integer','long':'BigInteger','bool':'Boolean','decimal':'Scaled100' if (c,name) in scaled else 'BigInteger','DateTime':'DB_DATETIME','byte[]':'LargeBinary'}[typ]
  if typ=='string' and name in {'Email','Name','Role','VerificationStatus','Status','Category'}:
   t='String(254)' if name=='Email' else 'String(191)' if name in {'Name','Category'} else 'String(64)'
  if typ=='byte[]': t='LARGE_BLOB'
  if (c,name) in refs:
   ref,delrule=refs[(c,name)]
   args=f'"{name}", {t}, ForeignKey("{ref}.Id", ondelete="{delrule}")'
  else: args=f'"{name}", {t}'
  opts=[]
  if name=='Id':opts+=['primary_key=True','autoincrement=True']
  else:opts.append('nullable='+str(nullable))
  if not default.strip() and not nullable and name!='Id' and typ in ('int','long','decimal','bool'):
   opts.append('default=False' if typ=='bool' else 'default=0')
  if default.strip() and default.strip()!='Array.Empty<byte>()':
   x=default.strip()
   if 'DateTime.UtcNow' in x:opts.append('default=utcnow')
   elif x=='true':opts.append('default=True')
   elif x=='false':opts.append('default=False')
   elif x.startswith('"'):opts.append('default='+x)
   elif re.fullmatch(r'\d+m?',x):opts.append('default='+x.rstrip('m'))
  lines.append(f'    {n}: Mapped[{"str" if typ=="string" else "int" if typ in ("int","long") else "bool" if typ=="bool" else "Decimal" if typ=="decimal" else "datetime" if typ=="DateTime" else "bytes"}{" | None" if nullable else ""}] = mapped_column({args}, {", ".join(opts)})')
 for cols,unique in index.get(c,[]):
  keys=cols.split(',');args=', '.join(f'"{x}"' for x in keys)
  lines.append(f'    __table_args__ = (Index("ix_{tables[c].lower()}_{"_".join(keys).lower()}", {args}, unique={unique}),)') if len(index.get(c,[]))==1 else None
 if len(index.get(c,[]))>1:
  lines.append('    __table_args__ = (')
  for cols,unique in index[c]:
   keys=cols.split(',');args=', '.join(f'"{x}"' for x in keys)
   lines.append(f'        Index("ix_{tables[c].lower()}_{"_".join(keys).lower()}", {args}, unique={unique}),')
  lines.append('    )')
 if c=='Payment':
  lines.extend(['    @property','    def outstanding(self):','        return (self.amount or Decimal(0)) - (self.amount_paid or Decimal(0))','', '    @property','    def awaiting_confirmation(self):','        return (self.amount_paid or Decimal(0)) - (self.confirmed_amount or Decimal(0))'])
 if c=='User':
  lines.extend(['    @property','    def is_verified(self):','        return self.verification_status == "verified"'])
 classes.append('\n'.join(lines))
out=Path(__file__).resolve().parents[1]/'app/models.py'
out.write_text(comments+'\n\n'.join(classes)+'\n')
print('Generated',len(classes),'models', sum(len(re.findall(r'mapped_column\(',x)) for x in classes),'fields ->',out)
