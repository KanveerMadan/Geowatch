"""Does weighted CE alone rescue Arm A, or is Dice also needed?"""
import sys, numpy as np, torch, torch.nn as nn, torch.nn.functional as F
sys.path.insert(0,".")
from experiments.band_reflectance.run_probe import (
    ProbeSeg, city_data, sample_coords, PATCH, IGNORE, LR, BATCH, CATEGORIES)
from experiments.harness.loco import folds, set_determinism

ck=torch.load("models/production/geowatch_production_model.pth",map_location="cpu",weights_only=False)
CW=ck["class_weights"].float()
dev="mps"

def dice(logits,targets,n=7,eps=1.0):
    valid=targets!=IGNORE
    if valid.sum()==0: return logits.sum()*0
    p=F.softmax(logits,1)
    t=targets.clone(); t[~valid]=0
    oh=F.one_hot(t,n).permute(0,3,1,2).float()
    m=valid.unsqueeze(1).float()
    p,oh=p*m,oh*m
    inter=(p*oh).sum((0,2,3)); denom=p.sum((0,2,3))+oh.sum((0,2,3))
    return 1.0-((2*inter+eps)/(denom+eps)).mean()

def build(mode,ch,seed,per=120):
    set_determinism(seed); rng=np.random.default_rng(seed)
    _,held,train=list(folds())[0]
    X,Y=[],[]
    for c in train:
        img,canv=city_data(c,mode)
        for (y,x) in sample_coords(canv,rng,per):
            X.append(img[:,y:y+PATCH,x:x+PATCH]); Y.append(canv[y:y+PATCH,x:x+PATCH])
    return torch.from_numpy(np.stack(X)).float(), torch.from_numpy(np.stack(Y)).long()

X,Y=build("rgb_stretch",3,1337)
for name,use_dice in [("weighted CE only",False),("weighted CE + Dice",True)]:
    set_determinism(1337)
    m=ProbeSeg(3).to(dev); opt=torch.optim.AdamW(m.parameters(),lr=LR)
    ce=nn.CrossEntropyLoss(weight=CW.to(dev),ignore_index=IGNORE)
    print(f"\nArm A, {name}:")
    m.train()
    for ep in range(10):
        tot=0;nb=0; order=torch.randperm(len(X))
        for i in range(0,len(X),BATCH):
            b=order[i:i+BATCH]; xb,yb=X[b].to(dev),Y[b].to(dev)
            opt.zero_grad(); lg=m(xb)
            l=ce(lg,yb) + (dice(lg,yb) if use_dice else 0)
            l.backward(); opt.step(); tot+=float(l); nb+=1
        if ep in (0,2,4,9): print(f"   epoch {ep:2d}  loss {tot/nb:.4f}")
