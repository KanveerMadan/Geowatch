import numpy as np
from experiments.urban_flood_ref.partial_water import wet_support


def test_real_wet_patch_survives_mixed_pixel_without_inventing_dry():
    fine=np.full((3,9),255,np.uint8);fine[1,1]=1;fine[1,7]=1
    urban=np.full(fine.shape,.5)
    occ=np.zeros(fine.shape);occ[0,8]=85
    positive,count=wet_support(fine,urban,occ)
    assert positive.tolist()==[[True,False,False]]
    assert count.tolist()==[[1,255,255]]
