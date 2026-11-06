import re,cairosvg
D="node_modules/@tabler/icons/icons/outline/"
def inner(n):
    s=open(D+n+".svg").read(); return re.search(r"<svg[^>]*>(.*)</svg>",s,re.S).group(1)
def icon(n,x,y,sz,col,sw=1.8):
    k=sz/24; return f'<g transform="translate({x-sz/2} {y-sz/2}) scale({k})" fill="none" stroke="{col}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">{inner(n)}</g>'
def badge(n,x,y,r,bg,fg):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{bg}"/>'+icon(n,x,y,r*1.15,fg)
F='font-family="Times New Roman, Times, serif"'
def t(x,y,s,sz=8,w="normal",c="#1b2a38",a="middle",it=False):
    return f'<text x="{x}" y="{y}" {F} font-size="{sz}" font-weight="{w}" fill="{c}" text-anchor="{a}"{" font-style=\"italic\"" if it else ""}>{s}</text>'
CM,CT,FAIL="#e4572e","#9bc53d","#d62828"
def chain(x,y,n,start=0,fade=1,step=13):
    o=""
    for i in range(n):
        m=(i+start)%2==0
        if i<n-1:o+=f'<line x1="{x+4}" y1="{y}" x2="{x+step-4}" y2="{y}" stroke="#8a97a6" stroke-width="0.9" opacity="{fade}"/>'
        o+=(f'<circle cx="{x}" cy="{y}" r="4" fill="{CM}" stroke="#333" stroke-width="0.5" opacity="{fade}"/>' if m else
            f'<rect x="{x-3.3}" y="{y-3.3}" width="6.6" height="6.6" rx="1" fill="{CT}" stroke="#333" stroke-width="0.5" opacity="{fade}"/>')
        x+=step
    return o
def panel(x,w,num,title,bg,ac):
    return (f'<rect x="{x}" y="6" width="{w}" height="188" rx="10" fill="{bg}" stroke="{ac}" stroke-width="1"/>'
            f'<rect x="{x}" y="6" width="{w}" height="24" rx="10" fill="{ac}"/><rect x="{x}" y="20" width="{w}" height="10" fill="{ac}"/>'
            f'<circle cx="{x+13}" cy="18" r="7.5" fill="white"/>'+t(x+13,21,str(num),8,"bold",ac)+t(x+25,22,title,10,"bold","white","start"))
def arrow(x0,x1,y=110):
    return f'<path d="M{x0} {y} L{x1} {y}" stroke="#44546a" stroke-width="1.6" marker-end="url(#a)"/>'
S=['<svg xmlns="http://www.w3.org/2000/svg" width="6.9in" height="2.0in" viewBox="0 0 690 200">',
 '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" fill="#44546a"/></marker></defs>',
 '<rect width="690" height="200" fill="white"/>']
# 1 agent
S+= [panel(4,128,1,"Agent runs a task","#eef5fc","#3b6ea5")]
S+= [badge("robot",40,62,17,"#d6e6f6","#3b6ea5"), badge("server",96,62,17,"#d6e6f6","#3b6ea5")]
S+= [f'<path d="M58 58 L78 58" stroke="#3b6ea5" stroke-width="1.2" marker-end="url(#a)"/><path d="M78 67 L58 67" stroke="#3b6ea5" stroke-width="1.2" marker-end="url(#a)"/>']
S+= [t(40,90,"agent",7.5,"bold"),t(96,90,"vLLM + cache",7.5,"bold")]
S+= [chain(22,110,8)]
S+= [t(68,130,"multi-turn BFCL task:",7.5,it=True),t(68,141,"model calls ● and tool calls ■",7),
     t(68,160,"road trip: distance, fuel,",7,c="#4a5a6a"),t(68,171,"refuel, engine, navigation",7,c="#4a5a6a")]
S+= [arrow(133,141)]
# 2 failure
S+= [panel(142,122,2,"A failure hits","#fdf1ec","#c0522b")]
for i,(ic,lab) in enumerate([("traffic-lights","rate limit"),("braces","bad JSON"),("tool","tool error"),("hourglass","timeout")]):
    x=176+(i%2)*56; y=54+(i//2)*44
    S+=[badge(ic,x,y,12,"#fadccf","#c0522b"),t(x,y+22,lab,7.5)]
S+= [chain(158,148,4), f'<g transform="translate(205 148)">'+icon("x",0,0,11,FAIL,3.2)+'</g>']
S+= [t(203,168,"early or late in the task",7.5,"bold"),t(203,180,"fired once, at a chosen call",7,c="#4a5a6a")]
S+= [arrow(265,273)]
# 3 decide
S+= [panel(274,108,3,"Decide","#f4f0fb","#6a4fa3")]
S+= [badge("brain",328,64,20,"#e3dbf4","#6a4fa3")]
S+= [t(328,98,"failure class",7.5),t(328,109,"+ work done (calls)",7.5)]
S+= ['<rect x="286" y="118" width="84" height="34" rx="6" fill="white" stroke="#6a4fa3" stroke-width="0.9"/>',
     t(328,132,"cost model",8,"bold"),t(328,145,"energy ÷ P(success)",7.5)]
S+= [t(328,168,"restart below a threshold,",7,c="#4a5a6a"),t(328,179,"resume above it",7,c="#4a5a6a")]
S+= [arrow(383,391)]
# 4 recover
S+= [panel(392,160,4,"Recover","#eef8f1","#2f8a57")]
rows=[("refresh","restart",0,7,1),("player-track-next","resume",50,2,1),("arrow-back-up","roll back",30,4,1)]
for i,(ic,name,off,n,f) in enumerate(rows):
    y=52+i*30
    S+=[badge(ic,410,y,10,"#d4efdd","#2f8a57"),t(424,y+3,name,7.5,"bold",a="start")]
    S+=[chain(472+off-(0 if off==0 else 0),y,n,start=0 if name!="resume" else 0,step=10)]
S+= ['<rect x="404" y="140" width="136" height="38" rx="6" fill="white" stroke="#2f8a57" stroke-width="0.9"/>']
S+= [icon("stack-2",420,152,13,"#2f8a57"),t(434,155,"warm: prefix cache kept",7.2,a="start")]
S+= [icon("zzz",420,170,12,"#7a8a9a"),t(434,173,"cold: prefix cache reset",7.2,a="start")]
S+= [arrow(553,561)]
# 5 measure
S+= [panel(562,124,5,"Measure","#f3f6f9","#44546a")]
S+= [badge("bolt",590,58,14,"#e2e8ef","#e09f1f"),t(608,55,"board energy",7.5,"bold",a="start"),t(608,65,"GPU included",7,a="start",c="#4a5a6a")]
S+= [badge("gauge",590,92,14,"#e2e8ef","#44546a"),t(608,89,"minus idle",7.5,"bold",a="start"),t(608,99,"per attempt",7,a="start",c="#4a5a6a")]
S+= [badge("clipboard-check",590,126,14,"#e2e8ef","#2f8a57"),t(608,123,"checker",7.5,"bold",a="start"),t(608,133,"goal successful?",7,a="start",c="#4a5a6a")]
S+= ['<rect x="572" y="150" width="104" height="34" rx="6" fill="#44546a"/>',t(624,164,"energy per",8.5,"bold","white"),t(624,177,"successful goal",8.5,"bold","white")]
S+= ['</svg>']
open("F0_overview_v3.svg","w").write("".join(S))
cairosvg.svg2pdf(url="F0_overview_v3.svg",write_to="F0_overview_v3.pdf")
cairosvg.svg2png(url="F0_overview_v3.svg",write_to="F0_overview_v3.png",dpi=300,output_width=2070)
