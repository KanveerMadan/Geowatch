from PIL import Image
import json

im0 = Image.open('data/pipeline_runs/capetown_20260702_164022/tiles/tile_0_0.png')
im1 = Image.open('data/pipeline_runs/capetown_20260702_164022/tiles/tile_0_512.png')
print('tile_0_0 size (w,h):', im0.size)
print('tile_0_512 size (w,h):', im1.size)

m = json.load(open('data/pipeline_runs/capetown_20260702_164022/masks.json'))
print('num masks:', len(m))
print('segment_ids:', [x['segment_id'] for x in m])

a = json.load(open('data/pipeline_runs/capetown_20260702_164022/annotations.json'))
anns = a['annotations']
print('num annotations:', len(anns))
print('annotation segment_ids:', [x['segment_id'] for x in anns])