"""Does the discriminative LR (encoder 1e-5 / decoder 3e-4) rescue Arm A?"""
import sys, numpy as np, torch, torch.nn as nn
sys.path.insert(0,".")
from experiments.band_reflectance.run_probe import (
    ProbeSeg, city_data, sample_coords, PATCH, IGNORE, BATCH)
from experiments.harness.loco import folds, set_determinism
from torch.optim.lr_scheduler import CosineAnnealingLR

ck=torch.load("models/production/geowatch_production_model.pth",map_location="cpu",weights_only=False)
CW=ck["class_weights"].float(); dev="mps"; EP=10

def build(mode,seed,per=120):
    set_determinism(seed); rng=np.random.default_rng(seed)
    _,held,train=list(folds())[0]; X,Y=[],[]
    for c in train:
        img,canv=city_data(c,mode)
        for (y,x) in sample_coords(canv,rng,per):
            X.append(img[:,y:y+PATCH,x:x+PATCH]); Y.append(canv[y:y+PATCH,x:x+PATCH])
    return torch.from_numpy(np.stack(X)).float(), torch.from_numpy(np.stack(Y)).long()

for mode,ch,label in [("rgb_stretch",3,"A_rgb_stretch"),("rgb_abs",3,"B_rgb_abs")]:
    X,Y=build(mode,1337)
    set_determinism(1337)
    m=ProbeSeg(ch).to(dev)
    opt=torch.optim.AdamW([{'params':m.encoder.parameters(),'lr':1e-5},
                           {'params':m.decoder.parameters(),'lr':3e-4}])
    sch=CosineAnnealingLR(opt,T_max=EP,eta_min=1e-6)
    ce=nn.CrossEntropyLoss(weight=CW.to(dev),ignore_index=IGNORE)
    print(f"\n{label}  (encoder lr 1e-5 / decoder lr 3e-4, weighted CE):")
    m.train()
    for ep in range(EP):
        tot=0;nb=0; order=torch.randperm(len(X))
        for i in range(0,len(X),BATCH):
            b=order[i:i+BATCH]; xb,yb=X[b].to(dev),Y[b].to(dev)
            opt.zero_grad(); l=ce(m(xb),yb); l.backward(); opt.step(); tot+=float(l.detach()); nb+=1
        sch.step()
        if ep in (0,2,4,9): print(f"   epoch {ep:2d}  loss {tot/nb:.4f}")
