import ast
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as N
from collections import defaultdict
p=Path(__file__).resolve().parents[1] / 'models' / 'performance_report_wizard.py'
source=ast.parse(p.read_text())
methods=next(n for n in source.body if isinstance(n,ast.ClassDef))
ns={'fields':N(Date=N(context_today=lambda self: date(2026,11,17))), 'defaultdict':defaultdict}
for name in ('_visit_rows','_counts'):
    node=next(x for x in methods.body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),ns)
class Rec(N):
    def with_context(self,**kwargs): return self
    def __bool__(self): return bool(getattr(self,'id',True))
    def __eq__(self, other): return isinstance(other,Rec) and self.id==other.id
class Recs(list):
    @property
    def ids(self): return [r.id for r in self]
    def filtered(self,fn): return Recs(x for x in self if fn(x))
    def __getitem__(self,k):
        x=super().__getitem__(k)
        if isinstance(k,slice): return Recs(x)
        return x
    def __getattr__(self,k):
        if len(self)==1: return getattr(self[0],k)
        return False
partners=[Rec(id=i) for i in range(1,11)]
user=Rec(id=100); today=date(2026,11,17); past=today-timedelta(days=1); future=today+timedelta(days=1)
empty=Rec(id=False)
line=lambda i,*cust: Rec(id=i,customer_ids=Recs(cust))
plan=lambda i,day,state,*lines: Rec(id=i,name=f'VP-{i}',visit_date=day,purpose='followup',state=state,target_line_ids=Recs(lines))
p1=plan(1,past,'approved',line(1,partners[0],partners[1],partners[2]),line(2,partners[0])); p2=plan(2,today,'approved',line(3,partners[3])); p3=plan(3,future,'approved',line(4,partners[4])); p4=plan(4,past,'submitted',line(5,partners[5])); p5=plan(5,past,'rejected',line(6,partners[6])); p6=plan(6,today,'approved',line(7,partners[7]));
tracker=lambda i,p: Rec(id=i,plan_id=p,name=f'T-{i}',visit_date=p.visit_date if p else today,purpose='followup',visited_line_ids=Recs(),target_line_ids=Recs(),total_distance_km=2)
t1=tracker(101,p1);t6=tracker(106,p6);t7=tracker(107,empty)
def check(i,t,partner,target,state): return Rec(id=i,tracker_id=t,partner_id=partner,target_line_id=target,state=state,checkin_time=datetime(2026,11,16,10),checkout_time=datetime(2026,11,16,11) if state=='checked_out' else False,duration_minutes=60 if state=='checked_out' else 0,meeting_outcome='completed' if state=='checked_out' else False,location_name='Office',checkin_latitude=23.1,checkin_longitude=90.1,notes='test',customer_feedback='',selfie_image=False)
c1=check(201,t1,partners[0],p1.target_line_ids[0],'checked_out'); c2=check(202,t1,partners[2],p1.target_line_ids[0],'checked_in'); c3=check(203,t6,partners[7],p6.target_line_ids[0],'checked_in'); c4=check(204,t7,partners[8],empty,'checked_out'); t1.visited_line_ids.append(Rec(id=1,checkin_id=c1,rating='5'))
w=N(partner_id=False); plans=Recs([p1,p2,p3,p4,p5,p6]); trackers=Recs([t1,t6,t7]); checkins=Recs([c1,c2,c3,c4]); rows=ns['_visit_rows'](w,user,plans,trackers,checkins); counts=ns['_counts'](w,rows)
assert counts=={'planned_visits':9,'completed_visits':1,'unplanned_visits':1,'pending_visits':2,'missed_visits':2,'in_progress_visits':1,'overdue_visits':1,'awaiting_approval_visits':1,'rejected_visits':1,'completion_percent':100/7}, counts
assert len(rows)==10
assert next(r for r in rows if r['checkin_id']==201)['rating']==5
assert len([r for r in rows if r['partner_id']==1])==2
assert [r['status'] for r in rows if r['partner_id']==1]==['completed','missed']
assert next(r for r in rows if r['partner_id']==9)['is_planned'] is False
assert len({r['checkin_id'] for r in rows if r['checkin_id']})==len([r for r in rows if r['checkin_id']])
# Customer filter: emulate Odoo search domain for check-ins, preserve duplicate target slots.
w.partner_id=partners[0]; rows2=ns['_visit_rows'](w,user,plans,trackers,Recs([c1])); assert len(rows2)==2 and all(r['partner_id']==1 for r in rows2)
assert ns['_counts'](w,[])['completion_percent']==0
print('PASS: planned target reconciliation, duplicate target, completed, missed, pending, overdue, in-progress, rejected, unapproved, unplanned, customer scope, ratings, empty denominator')
