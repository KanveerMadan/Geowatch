"""Copy the verified model/evidence files into a portable, cache-free study release."""
import argparse
import json
from pathlib import Path
import shutil
from .guard import authorize
from .handoff import make_index
from .package import sha


def publish(root, output):
    root=root.resolve();output=output.resolve()
    if root==output:raise ValueError('Choose a separate distribution directory')
    included=set()
    def copy(path):
        rel=Path(path)
        if rel.is_absolute() or '..' in rel.parts: raise ValueError('Invalid product path')
        src=root/rel
        if src.is_symlink() or not src.is_file():raise ValueError(f'Invalid source {rel}')
        dst=output/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.is_symlink():raise ValueError('Will not overwrite a symbolic link')
        if not dst.exists() or sha(dst)!=sha(src):shutil.copyfile(src,dst)
        included.add(rel.as_posix())
    for entry in make_index(root):
        base=entry['event_id'];authorize(base);u=entry['unit']
        prefix=Path('events')/u
        manifest=json.loads((root/prefix/'manifest.json').read_text())
        for path,digest in manifest['sha256'].items():
            if path!=f'refs/{u}.npz' and Path(path).parent!=prefix:raise ValueError('Out-of-scope product')
            if sha(root/path)!=digest:raise ValueError('Invalid product digest')
            copy(path)
        copy(prefix/'manifest.json')
        for ref in entry['references']:
            copy(ref['path'])
            if ref.get('receipt'):copy(ref['receipt'])
        if entry['historical']:
            for name in ['intensity.tif','receipt.json']:copy(Path('historical')/u/name)
        if entry['kind']=='event':
            for k in ['reviewed_refs','benchmark_refs','manual_refs','partial_water_refs']:
                path=Path(k)/(u+'.json')
                if (root/path).is_file():
                    info=json.loads((root/path).read_text());file=Path(info['file'])
                    if file!=Path(k)/(u+'.npz') or info['sha256']!=sha(root/file):raise ValueError('Sidecar mismatch')
                    copy(path);copy(file)
                    for field in ['source_raster','source_receipt','nonpermanent_support']:
                        if isinstance(info.get(field),str) and (root/info[field]).is_file():copy(info[field])
            for name in ['ufo_urban_wet_children.tif','ufo_surface_10m.tif','ufo_surface.tif','ufo_reference.json','maxar_review.json','maxar_review.tif','maxar_single_review.json','maxar_single_review.tif',
                         'weihui_reference.json','weihui_fo.tif','weihui_fu.tif','weihui_gt.tif']:
                path=Path('independent')/base/name
                if (root/path).is_file():copy(path)
        # Empty optical receipts document a searched date with no observable cells.
        for ext in ['tif','json']:
            path=Path('independent')/base/(('s2_control.' if entry['kind']=='pre_event_control' else 's2_event.')+ext)
            if (root/path).is_file():copy(path)
    # Auxiliary mask needed to reproduce a VHR-derived sidecar offline.
    for entry in make_index(root):
        id=entry['event_id'];authorize(id)
        path=Path('reviewed_refs')/(id+'_nonpermanent.tif')
        if (root/path).is_file():copy(path)
    manifest={rel:sha(output/rel) for rel in sorted(included)}
    (output/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return len(manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('source',type=Path);p.add_argument('dest',type=Path)
    a=p.parse_args();print('Verified distribution files:',publish(a.source,a.dest))
