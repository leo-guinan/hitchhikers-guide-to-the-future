from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import hashlib, json

SOURCE = Path('/var/folders/4c/gfmq85t93gggkbtkgzbkx_mr0000gn/T/TemporaryItems/NSIRD_screencaptureui_QLJBHY/Screenshot 2026-08-06 at 6.41.04\u202fPM.png')  # git-secret-ignore local screenshot path, not a secret
OUT = Path('/Users/leoguinan/hitchhikers-guide-to-the-future/artifacts/question-cards')
OUT.mkdir(parents=True, exist_ok=True)
SOURCE_COPY = OUT / 'source' / 'guide-search-quai-001-source.png'
SOURCE_COPY.parent.mkdir(parents=True, exist_ok=True)
SOURCE_COPY.write_bytes(SOURCE.read_bytes())
CARD = OUT / 'guide-search-quai-001.png'
RECEIPT = OUT / 'guide-search-quai-001.json'

fonts = [
    '/System/Library/Fonts/SFNS.ttf',
    '/System/Library/Fonts/HelveticaNeue.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
]
mono_fonts = [
    '/System/Library/Fonts/SFNSMono.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
]
def font(size, mono=False):
    for p in (mono_fonts if mono else fonts):
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

def fit_text(draw, text, f, max_width):
    words = text.split(); lines=[]; line=''
    for w in words:
        trial = (line+' '+w).strip()
        if draw.textbbox((0,0), trial, font=f)[2] <= max_width: line=trial
        else:
            if line: lines.append(line)
            line=w
    if line: lines.append(line)
    return lines

W,H = 1200,2050
im = Image.new('RGB',(W,H),(8,10,16)); d=ImageDraw.Draw(im)
# restrained evidence-card palette
cream=(242,236,220); gold=(226,184,86); dim=(151,157,169); orange=(205,112,78); line=(49,57,71)
# outer frame
d.rounded_rectangle((28,28,W-28,H-28), radius=22, outline=(72,79,91), width=2)
d.text((76,62),'QUESTION CARD / PROOF OF SEARCH',font=font(25,True),fill=gold)
d.text((76,105),'GUIDE / 001',font=font(22,True),fill=dim)
d.line((76,151,W-76,151),fill=line,width=2)
# question and compressed result
f_q=font(67); d.text((76,184),'Why @QuaiNetwork?',font=f_q,fill=cream)
d.text((80,278),'5 items over 496 days.',font=font(34),fill=gold)
lines=[
    'A bounded archive search returned five dated pieces',
    'across a 496-day interval. This card records the',
    'search result as evidence; it does not claim causality,',
    'performance, or investment value.',
]
y=330
for line_text in lines:
    d.text((80,y),line_text,font=font(25),fill=dim); y+=34
# metadata chips
chips=[('RANGE','2025-03-27 → 2026-08-05'),('RETRIEVAL','chroma-cloud'),('SOURCE','Guide / Leo Twitter archive')]
x=80; cy=494
for label,value in chips:
    box_w=max(250,d.textbbox((0,0),label+'  '+value,font=font(18,True))[2]+34)
    if x+box_w>W-80: x=80; cy+=58
    d.rounded_rectangle((x,cy,x+box_w,cy+39),radius=8,fill=(17,22,31),outline=line,width=1)
    d.text((x+16,cy+10),label+'  '+value,font=font(18,True),fill=dim)
    x+=box_w+12
# evidence crop
crop=Image.open(SOURCE).convert('RGB')
# retain the X header and the Guide result panel, remove bottom reaction chrome
crop=crop.crop((20,18,1200,1335))
maxw=1080
scale=maxw/crop.width
crop=crop.resize((maxw,int(crop.height*scale)),Image.Resampling.LANCZOS)
ex=(W-maxw)//2; ey=590
# shadow and frame
d.rounded_rectangle((ex-7,ey-7,ex+maxw+7,ey+crop.height+7),radius=14,fill=(2,3,6),outline=(90,75,45),width=2)
im.paste(crop,(ex,ey))
# footer
yf=ey+crop.height+32
d.line((76,yf,W-76,yf),fill=line,width=2)
d.text((76,yf+22),'RECEIPT',font=font(19,True),fill=gold)
d.text((76,yf+53),'guide-search-quai-001  ·  captured 2026-08-06 18:41:04',font=font(20,True),fill=cream)
d.text((76,yf+86),'Shareable evidence block · combine by receipt ID, not by unverified narrative.',font=font(18),fill=dim)
d.text((W-280,yf+22),'NOT A CLAIM OF VALUE',font=font(16,True),fill=orange)
im.save(CARD,optimize=True)
sha=hashlib.sha256(CARD.read_bytes()).hexdigest()
receipt={
  'receipt_id':'guide-search-quai-001',
  'artifact':str(CARD),
  'source_screenshot':str(SOURCE_COPY),
  'question':'Why @QuaiNetwork?',
  'result':'5 items over 496 days',
  'range':{'start':'2025-03-27','end':'2026-08-05','days':496},
  'retrieval':'chroma-cloud',
  'source':'guide.hitchhikersguidetothefuture.com/guide/',
  'captured_at_local_filename':'2026-08-06 18:41:04',
  'claim_boundary':'Evidence of a bounded search result at capture time; not evidence of causality, performance, ownership, or investment value.',
  'sha256':sha,
}
RECEIPT.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'card':str(CARD),'receipt':str(RECEIPT),'sha256':sha,'size_bytes':CARD.stat().st_size}))
