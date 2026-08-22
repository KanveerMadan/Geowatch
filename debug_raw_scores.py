import json

with open("data/pipeline_runs/dharavi_20260620_165553/result.json") as f:
    result = json.load(f)

# Look at raw all_scores for first 3 segments
for s in result["segments"][:3]:
    print(f"\nSegment {s['segment_id']} ({s['category']}):")
    scores = sorted(s["all_scores"].items(), key=lambda x: x[1], reverse=True)
    for cat, score in scores:
        print(f"  {score:.4f}  {cat}")
