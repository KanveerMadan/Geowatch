"""Resume cleared historical products and optical checks, serially, from manifests."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
import ee
from .guard import authorize
from .optical_ee import collect
from .run import run_unit, atomic_json


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('units',nargs='+');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=args.output
    for unit in args.units: authorize(unit)
    for unit in args.units:
        for control in (False,True):
            key=unit+'_control' if control else unit
            for action in ('radar','optical'):
                if action=='optical' and not (root/'events'/key/'manifest.json').is_file(): continue
                for attempt in range(5):
                    try:
                        with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
                            fcntl.flock(lock,fcntl.LOCK_EX)
                            ee.Initialize(project=os.environ['GEE_PROJECT_ID'])
                            if action=='radar': run_unit(unit,root,control)
                            else: collect(unit,root,control)
                        break
                    except (ee.EEException, ConnectionError,TimeoutError) as error:
                        transient=any(x in str(error).lower() for x in ('timeout','timed out','quota','429','socket','503','temporarily','connection'))
                        if transient and attempt<4: time.sleep(2**(attempt+2));continue
                        failures=root/'failures';failures.mkdir(exist_ok=True,parents=True)
                        atomic_json(failures/(key+'_'+action+'.json'),{'unit':unit,'control':control,'stage':action,
                                    'type':type(error).__name__,'reason':str(error)[:500]})
                        print(key,action,'FAILED',error,flush=True)
                        break

if __name__=='__main__':main()
