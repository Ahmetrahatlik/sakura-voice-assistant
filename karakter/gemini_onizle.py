import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onizle_renk import recolor
from PIL import Image, ImageDraw, ImageFont
D = os.path.expanduser("~/.claude/sakura-deneme/src/poses/sd/")
H = os.path.dirname(os.path.abspath(__file__))
font = ImageFont.truetype("arial.ttf", 22)
box=(135,100,257,215); z=3; w,h=(box[2]-box[0])*z,(box[3]-box[1])*z
items=[("eski kapalı göz",D+"goz_kapali.png"),("YENİ kapalı göz",H+"/yeni/goz_kapali.png"),("eski kapalı ağız",D+"agiz_kapali.png"),("YENİ kapalı ağız",H+"/yeni/agiz_kapali.png"),("eski düşünceli",D+"ifade_dusunce.png"),("YENİ düşünceli",H+"/yeni/ifade_dusunce.png")]
G=Image.new("RGB",(2*(w+8),3*(h+34)),(30,30,30)); dr=ImageDraw.Draw(G)
for i,(t,f) in enumerate(items):
    x,y=(i%2)*(w+8),(i//2)*(h+34)
    a=np.array(Image.open(f).convert("RGBA")); r=Image.fromarray(recolor(a,"#2e2a3a"))
    G.paste(r.convert("RGB").crop(box).resize((w,h),Image.LANCZOS),(x,y+34)); dr.text((x+6,y+4),t,font=font,fill=(255,230,80))
G.save(os.path.join(os.path.dirname(H), sys.argv[1] if len(sys.argv)>1 else "gemini_onizleme.png"))
