"""Write the latest DEV comparison (results/dev_cv_r3.json) into STATUS.md, in plain words. Idempotent."""
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(HERE, "results", "dev_cv_r3.json")
S = os.path.join(HERE, "STATUS.md")
NAMES = {"fluvial": "River", "flash_flood": "Flash", "waterlogging": "Waterlogging", "pluvial": "Rain",
         "coastal": "Coastal", "compound": "Compound"}
PROVISIONAL = set()          # flash and waterlogging reached their 50-unit build targets (R32)
BASELINES = ("elev", "hand")
BEGIN, END = "<!-- DEV-CV:BEGIN -->", "<!-- DEV-CV:END -->"


def main():
    if not os.path.exists(R):
        return 0
    r = json.load(open(R))
    when = dt.datetime.fromtimestamp(os.path.getmtime(R)).strftime("%Y-%m-%d %H:%M")
    out = [BEGIN, f"## DEV comparison (auto-updated {when}; leave-region-out CV, DEV units only, reserve untouched)", "",
           "- **gain** is the method's mean within-unit AUC minus the better of elevation and HAND (the bar's comparison), with its 95 % cluster-bootstrap CI.",
           "- **vs elevation** is the method's mean AUC minus elevation's.",
           "- **chosen** is picked by the pre-registered rule: highest lower CI bound, ties within 0.005 go to the simpler method.",
           "- **A type is ready only if a non-baseline method clears the CI and reaches AUC 0.70.** If the rule picks elevation or HAND itself, no method beats the baseline on DEV.", ""]
    for ty in ("fluvial", "flash_flood", "waterlogging", "pluvial", "coastal", "compound"):
        b = r.get("by_type", {}).get(ty, {})
        tag = " (provisional)" if ty in PROVISIONAL else ""
        if "candidates" not in b:
            out += [f"### {NAMES[ty]}{tag}: {b.get('units', 0)} units, too few to compare", ""]
            continue
        c = b["candidates"]
        e = c.get("elev", {}).get("mean_auc")
        out += [f"### {NAMES[ty]}{tag}: {b['units']} units, {b.get('clusters', '?')} clusters; chosen **{b['chosen']}**", "",
                "| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |", "|---|---|---|---|---|---|"]
        for k, v in c.items():
            ma = v.get("mean_auc")
            ve = None if (ma is None or e is None) else ma - e
            ci = v.get("ci") or [None, None]
            ok = "yes" if ci[0] is not None and ci[0] > 0 else "no"
            out.append(f"| {k} | {ma if ma is None else round(ma, 3)} | {'' if ve is None else f'{ve:+.3f}'} | "
                       f"{v.get('gain') if v.get('gain') is None else f'{v['gain']:+.3f}'} | {ci} | {ok} |")
        learned = {k: v for k, v in c.items() if k not in BASELINES}
        best = max(learned, key=lambda k: ((learned[k].get("ci") or [-9])[0] or -9)) if learned else None
        miss = []
        if b["chosen"] in BASELINES:
            bl = learned.get(best, {})
            miss.append(f"no method beats the baseline: the best learned method, {best}, gains "
                        f"{bl.get('gain', 0):+.3f} with CI {bl.get('ci')}")
        else:
            ch = c[b["chosen"]]
            if (ch.get("mean_auc") or 0) < 0.70:
                miss.append(f"mean AUC {round(ch.get('mean_auc'), 3)} is below 0.70")
            if not ((ch.get("ci") or [0])[0] or 0) > 0:
                miss.append("the gain's CI does not clear 0")
        if b["units"] < 5:
            miss.append("fewer than 5 units")
        out += ["", "- **Still missing:** " + ("; ".join(miss) if miss else "nothing on DEV; the reserve test decides") + ".", ""]
    out.append(END)
    s = open(S).read()
    block = "\n".join(out)
    if BEGIN in s:
        s = s[:s.index(BEGIN)] + block + s[s.index(END) + len(END):]
    else:
        s = s.rstrip() + "\n\n" + block + "\n"
    open(S, "w").write(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
