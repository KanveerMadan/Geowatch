"""Is Arm A diverging, or just slow? Log the loss trajectory for A vs B."""
import sys, numpy as np, torch, torch.nn as nn
sys.path.insert(0,".")
from experiments.band_reflectance.run_probe import (
    ProbeSeg, city_data, sample_coords, PATCH, IGNORE, LR, BATCH, CATEGORIES)
from experiments.harness.loco import folds, set_determinism

dev="mps"
for arm,mode,ch in [("A_rgb_stretch","rgb_stretch",3),("B_rgb_abs","rgb_abs",3)]:
    set_determinism(1337)
    rng=np.random.default_rng(1337)
    _,held,train = list(folds())[0]
    X,Y=[],[]
    for c in train:
        img,canv=city_data(c,mode)
        for (y,x) in sample_coords(canv,rng,120):
            X.append(img[:,y:y+PATCH,x:x+PATCH]); Y.append(canv[y:y+PATCH,x:x+PATCH])
    X=torch.from_numpy(np.stack(X)).float(); Y=torch.from_numpy(np.stack(Y)).long()
    m=ProbeSeg(ch).to(dev); opt=torch.optim.AdamW(m.parameters(),lr=LR)
    lf=nn.CrossEntropyLoss(ignore_index=IGNORE)
    print(f"\n{arm}: input mean={X.mean():.4f} std={X.std():.4f}  n={len(X)}")
    m.train()
    for ep in range(10):
        tot=0;nb=0; order=torch.randperm(len(X))
        for i in range(0,len(X),BATCH):
            b=order[i:i+BATCH]; xb,yb=X[b].to(dev),Y[b].to(dev)
            opt.zero_grad(); l=lf(m(xb),yb); l.backward(); opt.step()
            tot+=l.item(); nb+=1
        if ep in (0,1,2,4,9): print(f"   epoch {ep:2d}  loss {tot/nb:.4f}")
