from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle, FancyArrowPatch
import numpy as np
import sys
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)

import os
if os.environ.get('RAF_FONT_DIR'):
 for font_file in Path(os.environ['RAF_FONT_DIR']).glob('*.ttf'):
  font_manager.fontManager.addfont(str(font_file))
font=font_manager.findfont('Arial',fallback_to_default=False)
plt.rcParams.update({'font.family':'Arial','font.size':8.5,'axes.labelsize':8.5,'xtick.labelsize':8,'ytick.labelsize':8,'text.color':'black','axes.labelcolor':'black','xtick.color':'black','ytick.color':'black','pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'savefig.facecolor':'white'})
colors=['#B8743C','#3B5A8C','#6E8B3D','#6E8B3D'];marks=['o','s','^','D'];labels=['Restart, warm','Resume, warm','Rollback, warm','Rollback, cold']
def save(fig,name):
 fig.savefig(out/(name+'.pdf'));fig.savefig(out/(name+'.png'),dpi=180);plt.close(fig)
# Values transcribed from v4 Table 4 / original generated e1 and e1b tables.
counts=np.array([[56,56,56,56],[47,44,56,48],[46,52,52,54],[44,52,56,58]])
epg=np.array([[1288,1352,1862,1822.5],[1715.5,1694,1289,1509],[1384.5,1313,1516,1455],[1583.5,1374.5,1496,1434]])/1000
fig=plt.figure(figsize=(7,2.8));gs=fig.add_gridspec(1,3,width_ratios=[1.55,1,1],left=.075,right=.99,bottom=.27,top=.77,wspace=.49)
axes=[fig.add_subplot(gs[i]) for i in range(3)]
for i in range(4):
 axes[0].plot(np.arange(4)+(i-1.5)*.12,counts[i],ls='none',marker=marks[i],ms=4,markerfacecolor='white' if i==3 else colors[i],color=colors[i],label=labels[i])
 for j,idx in enumerate([[0,2],[1,3]],1):axes[j].plot([0,1],epg[i,idx],color=colors[i],marker=marks[i],ms=3.5,lw=1,ls='--' if i==3 else '-',markerfacecolor='white' if i==3 else colors[i])
axes[0].set(ylim=(0,63),yticks=[0,20,40,60],xticks=range(4),xticklabels=['Early\nmodel','Early\ntool','Late\nmodel','Late\ntool'],ylabel='Correct goals (out of 60)')
axes[0].set_title('(a) Correctness',loc='left',fontsize=9,pad=8)
for a,title in zip(axes[1:],['(b) Model failures','(c) Tool failures']):
 a.set(xticks=[0,1],xticklabels=['Early','Late'],ylim=(1.2,2.02),yticks=[1.2,1.4,1.6,1.8,2.0]);a.set_title(title,loc='left',fontsize=9,pad=8)
axes[1].set_ylabel('Energy per successful goal (kJ)')
fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',ncol=4,frameon=False,handletextpad=.35,columnspacing=1.1,bbox_to_anchor=(.5,1.0),fontsize=8.5)
save(fig,'recovery-results')
# Saved macro summaries only, no newly estimated uncertainty.
fig,axs=plt.subplots(2,1,figsize=(3.4,3.55));fig.subplots_adjust(left=.24,right=.95,bottom=.13,top=.91,hspace=.95)
a=axs[0];a.barh([1,0],[14,92],xerr=[1,2],color=['#bfbfbf','#777777'],height=.48,error_kw={'lw':.8,'capsize':2},edgecolor='black',linewidth=.5)
a.set(yticks=[1,0],yticklabels=['Uncached\ninput tokens','Energy'],xlim=(0,100),xticks=[0,50,100],xlabel='Warm as a share of cold (%)');a.set_title('(a) Recovery window',loc='left',fontsize=9)
a=axs[1];a.axvspan(0,7.333,color='#e8e8e8',zorder=0)
a.errorbar([2.048,4.096,8.192,16.384,24.576,32.672],[.70,.54,.34,.20,.14,.10],yerr=[[.03,.03,.01,0,0,0],[.02,.02,.01,.01,.01,.01]],fmt='-o',color='black',ms=3,lw=1,capsize=2)
a.set(xlim=(0,34),ylim=(0,.85),xticks=[0,8,16,24,32],yticks=[0,.4,.8],xlabel='Context (thousand tokens)',ylabel='Cached / uncached\nenergy');a.set_title('(b) Isolated model call',loc='left',fontsize=9)
a.annotate('Task upper bound',xy=(7.333,.30),xytext=(11,.65),fontsize=8,arrowprops={'arrowstyle':'->','lw':.6})
save(fig,'cache-effects')
fig,ax=plt.subplots(figsize=(3.4,2.0));fig.subplots_adjust(left=.29,right=.96,bottom=.30,top=.95)
ax.axvline(0,c='#777777',lw=.7,ls='--');v=np.array([22,7.6,3.2]);lo=np.array([11.9,2,-1.9]);hi=np.array([31.8,12.5,6.6])
ax.errorbar(v,[2,1,0],xerr=np.array([v-lo,hi-v]),fmt='o',color='black',ms=4,elinewidth=1,capsize=2)
ax.set(yticks=[2,1,0],yticklabels=['Restart\n(warm)','Resume\n(warm)','Rollback\n(cold)'],ylim=(-.55,2.55),xlim=(-5,35),xticks=[0,10,20,30],xlabel='EpG saving versus fixed policy (%)')
save(fig,'heldout-policy')
print('Generated three published data figures; font:',font)
