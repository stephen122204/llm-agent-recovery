"""Mechanism schematics only. No experimental values or proportional durations."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle

import os
if os.environ.get('RAF_FONT_DIR'):
 for font_file in Path(os.environ['RAF_FONT_DIR']).glob('*.ttf'):
  font_manager.fontManager.addfont(str(font_file))
font_manager.findfont('Arial', fallback_to_default=False)
plt.rcParams.update({'font.family':'Arial','font.size':8.5,'text.color':'black','pdf.fonttype':42,'ps.fonttype':42,'savefig.facecolor':'white'})
import sys
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
def save(fig,name):
 fig.savefig(out/(name+'.pdf'),bbox_inches=None)
 fig.savefig(out/(name+'.png'),dpi=180)
 plt.close(fig)
# The three turn columns share the same x coordinates in every row.
fig=plt.figure(figsize=(7,2.12));ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,7),ylim=(0,2.12));ax.axis('off')
x=1.23;w=1.10;gap=.06;last=.64
ax.text(.04,1.97,'Recovery',weight='bold',va='center')
ax.text(x,1.97,'Completed work before the failure',weight='bold',va='center')
ax.text(5.00,1.97,'Tool state restored to',weight='bold',va='center')
for i in range(3):ax.text(x+i*(w+gap)+(w if i<2 else last)/2,1.73,f'Turn {i+1}',ha='center',va='center')
for row,(name,y) in enumerate([('Before failure',1.48),('Restart',1.13),('Rollback',.78),('Resume',.43)]):
 ax.text(.04,y,name,va='center',weight='normal' if row==0 else 'bold')
 for i in range(3):
  repeat=row==1 or (row==2 and i==2)
  ax.add_patch(Rectangle((x+i*(w+gap),y-.105),w if i<2 else last,.21,facecolor='white' if repeat else '#e6e6e6',edgecolor='#333333',hatch='////' if repeat else None,lw=.6))
 if row==0:
  xx=x+2*(w+gap)+last
  ax.plot(xx,y,marker='x',color='black',ms=6,mew=1)
  ax.text(xx+.10,y,'Failed call',va='center',fontsize=8)
 else:
  ax.text(5.00,y,['','Initial task state','Start of failed turn','Before failed call'][row],va='center')
 if row==3:ax.text(x+2*(w+gap)+last+.10,y,'+ notice',va='center',fontsize=8)
for xx,label,hatch in [(1.23,'Kept in conversation',None),(3.58,'Repeated after recovery','////')]:
 ax.add_patch(Rectangle((xx,.08),.22,.105,facecolor='#e6e6e6' if hatch is None else 'white',edgecolor='#333333',hatch=hatch,lw=.6))
 ax.text(xx+.29,.1325,label,va='center',fontsize=8)
save(fig,'recovery-operations')
# Clear sequence with each measured window aligned to its own label.
fig=plt.figure(figsize=(3.4,1.48));ax=fig.add_axes([0,0,1,1]);ax.set(xlim=(0,3.4),ylim=(0,1.48));ax.axis('off')
ax.text(.04,1.35,'Energy counted for one goal',weight='bold',va='center')
boxes=[(.04,.86,'Attempt 1\nuntil failure',True),(1.06,1.18,'Choose recovery\nRestore tools\nPrepare cache',False),(2.40,.94,'Recovery\nattempt',True)]
for x,w,label,metered in boxes:
 ax.add_patch(Rectangle((x,.48),w,.59,facecolor='#e6e6e6' if metered else 'white',edgecolor='#333333',lw=.6,linestyle='-' if metered else '--'))
 ax.text(x+w/2,.775,label,ha='center',va='center',fontsize=8)
 ax.text(x+w/2,.32,'Measured' if metered else 'Not metered',ha='center',va='center',fontsize=8)
for start,end in [(.90,1.06),(2.24,2.40)]:
 ax.annotate('',xy=(end-.015,.775),xytext=(start+.015,.775),arrowprops={'arrowstyle':'->','lw':.65,'shrinkA':0,'shrinkB':0,'mutation_scale':7})
ax.text(1.70,.08,'Above-idle board energy of both attempts',ha='center',va='center',fontsize=8)
save(fig,'measurement-windows')
