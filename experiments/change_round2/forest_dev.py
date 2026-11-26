from .data import HERE,connect,forest_cover,history,read,save
from .forest import forest
def main():
    ee=connect()
    cohort=read(HERE.parent/"change_history/known_change_manifest.json")
    output={}
    for region in cohort["regions"]:
        if region["name"] not in ("chaco_paraguay","sumatra_indonesia"): continue
        cells=[c["xy"] for c in region["cells"]]
        rows=history(ee,region["crs"],cells,"2019-01-01","2022-01-01")
        out=[]
        shares=forest_cover(ee,region["crs"],cells,"2021-01-01")
        for c,h,share in zip(region["cells"],rows,shares,strict=True):
            r=forest(h,"2021-01-01","2022-01-01",share)
            out.append({"cell":c["id"],"forest_share":share,"domain":r["domain"],"confirmed_sources":sorted({v["source"] for v in r["confirmed"]}),
                        "observed_sources":r["observed_sources"],"earliest":next((v["day"] for v in r["confirmed"]),None)})
        output[region["name"]]=out
    save(HERE/"forest_dev.json",{"regions":output,"zero_baseline_hits":0})
if __name__=="__main__":main()
