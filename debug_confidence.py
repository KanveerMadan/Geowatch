import json

with open("data/pipeline_runs/dharavi_20260620_150817/result.json") as f:
    result = json.load(f)

confidences = [s["confidence"] for s in result["segments"]]
print(f"Min confidence: {min(confidences):.4f}")
print(f"Max confidence: {max(confidences):.4f}")
print(f"Mean confidence: {sum(confidences)/len(confidences):.4f}")

road_scores = [s["road_access_score"] for s in result["segments"]]
print(f"\nRoad access scores - unique values: {set(road_scores)}")
