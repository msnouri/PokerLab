"""Original fixed-layout table artwork for the interactive practice game."""
from PIL import Image, ImageDraw
from .vision import card_image, font, Profile

WIDTH, HEIGHT = 1200, 730


def render_table(view):
    im=Image.new("RGB",(WIDTH,HEIGHT),"#0d171f")
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((72,85,1128,602),radius=230,fill="#20343b",outline="#39515a",width=3)
    d.rounded_rectangle((91,103,1109,584),radius=218,fill="#143e3d",outline="#285450",width=2)
    d.rounded_rectangle((106,118,1094,568),radius=200,outline="#23504a",width=2)
    d.text((WIDTH//2,153),"POKER / LAB",fill="#6e9690",font=font(19),anchor="mm")
    d.text((WIDTH//2,181),f"HAND {view['hand_no']:03d}   ·   10 / 20   ·   PRACTICE CHIPS",fill="#91aaa5",font=font(15),anchor="mm")
    d.text((WIDTH//2,230),"POT",fill="#9cb5ad",font=font(13),anchor="mm")
    d.text((WIDTH//2,260),str(view["pot"]),fill="#f2d596",font=font(32),anchor="mm")
    for j in range(5):
        x=414+j*76
        if j < len(view["board"]):
            im.paste(card_image(view["board"][j]),(x,300))
        else:
            d.rounded_rectangle((x,300,x+63,387),radius=5,fill="#184441",outline="#28534d")
    hero=view["hero"]
    # Physical seats rotate around the fixed hero at the bottom.
    positions=[(600,625),(220,480),(214,201),(600,63),(984,201),(980,480)]
    for offset,(x,y) in enumerate(positions):
        seat=(hero+offset)%6
        mine=seat==hero
        active=view["active"][seat]
        fill="#243c44" if mine else "#15262e"
        outline="#d6b878" if mine and view["pending"] else "#38515a"
        d.rounded_rectangle((x-100,y-34,x+100,y+33),radius=14,fill=fill,outline=outline,width=2)
        name="YOU" if mine else f"SEAT {seat+1}"
        if not active and view["pending"]:
            name+=" · FOLDED"
        d.text((x,y-14),name,fill="#c9d8d9" if active or mine else "#607981",font=font(13),anchor="mm")
        d.text((x,y+12),str(view["stacks"][seat]),fill="#ffffff",font=font(20),anchor="mm")
        if seat==5:
            d.ellipse((x+108,y-10,x+130,y+12),fill="#dfc68c")
            d.text((x+119,y+1),"D",fill="#17252a",font=font(12),anchor="mm")
        if not mine and active and view["pending"]:
            im.paste(card_image(None,(25,34)),(x-28,y+41))
            im.paste(card_image(None,(25,34)),(x+3,y+41))
    im.paste(card_image(view["hole"][0]),(526,493))
    im.paste(card_image(view["hole"][1]),(610,493))
    label="Your decision" if view["pending"] else f"Hand complete · {view['net']:+d} chips"
    d.text((600,674),label,fill="#b7cfca",font=font(15),anchor="mm")
    obs=view.get("observation") or {}
    for j,(key,name) in enumerate((("to_call","CALL COST"),("bet","YOUR BET"),("min_raise_to","MIN RAISE TO"),("max_raise_to","MAX RAISE TO"))):
        x=335+j*175
        d.text((x,696),name,fill="#829da8",font=font(10),anchor="mm")
        value=obs.get(key)
        d.text((x,717),str(value) if value is not None else "NONE",fill="#ecf2ee",font=font(21),anchor="mm")
    return im


def standard_profile():
    regions={"hole_1":[526/WIDTH,493/HEIGHT,64/WIDTH,88/HEIGHT],
             "hole_2":[610/WIDTH,493/HEIGHT,64/WIDTH,88/HEIGHT],
             "pot":[520/WIDTH,240/HEIGHT,160/WIDTH,42/HEIGHT],
             "stack":[540/WIDTH,627/HEIGHT,120/WIDTH,25/HEIGHT]}
    for i in range(5):
        regions[f"board_{i+1}"]=[(414+i*76)/WIDTH,300/HEIGHT,64/WIDTH,88/HEIGHT]
    for j,key in enumerate(("to_call","bet","min_raise_to","max_raise_to")):
        regions[key]=[(260+j*175)/WIDTH,704/HEIGHT,150/WIDTH,25/HEIGHT]
    return Profile(name="Poker Lab practice table",regions=regions)
