import json
import os

runs_dir = "data/pipeline_runs"
latest_run = sorted(os.listdir(runs_dir))[-1]
result_path = os.path.join(runs_dir, latest_run, "result.json")

with open(result_path) as f:
    result = json.load(f)

confidences = [s["confidence"] for s in result["segments"]]
print(f"Run: {latest_run}")
print(f"Min confidence: {min(confidences):.4f}")
print(f"Max confidence: {max(confidences):.4f}")
print(f"Mean confidence: {sum(confidences)/len(confidences):.4f}")
print(f"\nDominant category: {result['summary']['dominant_category']}")
print(f"Category breakdown: {result['summary']['category_counts']}")
print(f"Flood risk segments: {result['summary']['flood_risk_segments']}")
