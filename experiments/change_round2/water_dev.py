"""Compare the candidate with silence on previously tested Sylhet cells."""
from .data import HERE, connect, history, permanence, read, save
from .water import water

def main():
    m=read(HERE.parent/"change_history/monsoon_water_manifest.json")
    cells=[]
    for key in m["cells"]:
        _,x,y=key.split("/")
        cells.append((int(x),int(y)-100))
    ee=connect(); crs="EPSG:32646"
    rows=history(ee,crs,cells,"2022-02-01","2022-07-01")
    mask=permanence(ee,crs,cells,"2022-06-01")
    output=[]
    for key,h,p in zip(m["cells"],rows,mask,strict=True):
        d=water(h,"2022-06-01","2022-07-01",p)
        output.append({"cell":key,"confirmation":next(iter(d["gain"]),None),"observable":"gain" in d["observed_targets"],"prior_water":p})
    save(HERE/"water_dev.json",{"cells":output,"zero_baseline_hits":0})
if __name__=="__main__": main()
