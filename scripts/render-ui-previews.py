from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path('docs/screenshots')
try:
    font=ImageFont.truetype('DejaVuSans.ttf',18)
except OSError:
    font=ImageFont.load_default(size=18)
names=['01-save-browser','02-pokemon-box','03-start-trade','04-confirm-save','05-recovery','06-complete']
contact=Image.new('RGB',(1320,1160),'#e6ebe5')
for i,name in enumerate(names):
    panel=Image.new('RGB',(424,530),'#e6ebe5'); d=ImageDraw.Draw(panel)
    d.text((12,4),name[3:].replace('-',' ').title(),font=font,fill='#153b40')
    for which,y in [('top',34),('bottom',282)]:
        im=Image.open(root/f'{name}-{which}.ppm'); im.save(root/f'{name}-{which}.png')
        panel.paste(im,((424-im.width)//2,y))
    panel.save(root/f'{name}.png'); contact.paste(panel,(12+i%3*440,12+i//3*574))
contact.save(root/'overview.png')

settings_names=['07-home','08-settings','09-connected','10-resume-home']
settings=Image.new('RGB',(880,1120),'#e6ebe5')
for i,name in enumerate(settings_names):
    panel=Image.new('RGB',(424,530),'#e6ebe5'); d=ImageDraw.Draw(panel)
    d.text((12,4),name[3:].replace('-',' ').title(),font=font,fill='#153b40')
    for which,y in [('top',34),('bottom',282)]:
        im=Image.open(root/f'{name}-{which}.ppm'); im.save(root/f'{name}-{which}.png')
        panel.paste(im,((424-im.width)//2,y))
    panel.save(root/f'{name}.png'); settings.paste(panel,(12+i%2*440,12+i//2*560))
settings.save(root/'settings-overview.png')
