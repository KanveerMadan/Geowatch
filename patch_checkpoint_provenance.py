import torch

path = "models/production/geowatch_production_model.pth"  # adjust if your downloaded file landed elsewhere
checkpoint = torch.load(path, map_location="cpu")

checkpoint["loco_mean_miou"] = 0.3037   # fresh 11-fold mean from tonight's separation-loss LOCO run
checkpoint["loco_std_miou"] = None      # fill in later if you want the real std computed
checkpoint["loco_n_folds"] = 11

torch.save(checkpoint, path)
print("Checkpoint provenance updated.")
print(f"  loco_mean_miou = {checkpoint['loco_mean_miou']}")
print(f"  loco_n_folds   = {checkpoint['loco_n_folds']}")