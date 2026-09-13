"""Is it purely input magnitude? Rescale Arm A to Arm B's mean and retry."""
import sys, numpy as np, torch, torch.nn as nn
sys.path.insert(0,".")
from experiments.band_reflectance.run_probe import (
    ProbeSeg, city_data, sample_coords, PATCH, IGNORE, BATCH)
from experiments.harness.loco import set_determinism

ck=torch.load("models/production/geowatch_production_model.pth",map_location="cpu",weights_only=False)
CW=ck["class_weights"].float(); dev="mps"; EP=10
TEN=["capetown","dhaka","dharavi","guatemala","hcmc","jakarta","kigali","lagos","nairobi","nusantara"]

def patches(mode,per=120):
    rng=np.random.default_rng(1337); X,Y=[],[]
    for c in TEN:
        img,canv=city_data(c,mode)
        for (y,x) in sample_coords(canv,rng,per):
            X.append(img[:,y:y+PATCH,x:x+PATCH]); Y.append(canv[y:y+PATCH,x:x+PATCH])
    return torch.from_numpy(np.stack(X)).float(), torch.from_numpy(np.stack(Y)).long()

Xa,Ya=patches("rgb_stretch")
variants=[("A as-is (mean %.3f)"%Xa.mean(), Xa),
          ("A x0.27 -> B's mean", Xa*0.27),
          ("A standardised (0 mean, unit std)", (Xa-Xa.mean())/Xa.std())]
for label,X in variants:
    set_determinism(1337)
    m=ProbeSeg(3).to(dev)
    opt=torch.optim.AdamW([{'params':m.encoder.parameters(),'lr':1e-5},
                           {'params':m.decoder.parameters(),'lr':3e-4}])
    ce=nn.CrossEntropyLoss(weight=CW.to(dev),ignore_index=IGNORE)
    m.train(); first=last=None
    for ep in range(EP):
        tot=0;nb=0; order=torch.randperm(len(X))
        for i in range(0,len(X),BATCH):
            b=order[i:i+BATCH]; xb,yb=X[b].to(dev),Ya[b].to(dev)
            opt.zero_grad(); l=ce(m(xb),yb); l.backward(); opt.step(); tot+=float(l.detach()); nb+=1
        if ep==0: first=tot/nb
        last=tot/nb
    print(f"  {label:<36} loss {first:.4f} -> {last:.4f}  {'LEARNS' if last<first*0.6 else 'FLAT'}")
