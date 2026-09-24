"""
ingestion/resnet_model.py
==========================
GeoWatchResNetSeg architecture — ResNet50 (torchgeo SSL4EO-S12 MoCo,
Sentinel-2 RGB pretrained) encoder + DeepLabV3+-style decoder.

Extracted directly from the training notebook
(geowatch_segformer_finetune_UPDATED.ipynb, the "Encoder swap" cell) —
no logic changes. This is the exact architecture the production
checkpoint (geowatch_production_model.pth) was trained with. If you
ever change this file, the existing checkpoint's state_dict will no
longer load correctly (shape mismatches) — architecture and checkpoint
must always change together.

WHY this architecture (see master prompt Section 6 for full history):
Clay v1 was rejected (flat ViT, incompatible with a hierarchical
decoder). SegFormer-B2 with a frozen ImageNet encoder was tried and
superseded (ImageNet features never saw satellite imagery, and
freezing meant the decoder alone had to bridge that gap — this was the
source of the old ~0.057 mIoU baseline). This ResNet50 backbone is
genuinely satellite-domain-pretrained (MoCo self-supervised on
Sentinel-2 RGB) and is fully fine-tuned here, not frozen.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchgeo.models import ResNet50_Weights, resnet50

# ── Encoder band contract — verified, and asserted at load time ─────────────
#
# The pretrained encoder is SENTINEL2_RGB_MOCO, which is a THREE-band
# checkpoint (in_chans=3, bands ['B4','B3','B2'] = Red, Green, Blue). It is NOT
# SENTINEL2_ALL_MOCO (13-band), and there is no slicing of a 13-band conv1 down
# to 6 channels anywhere in this codebase -- conv1.weight is (64, 3, 7, 7) in
# both the freshly-loaded encoder and the deployed production checkpoint.
#
# So the model sees Red, Green, Blue only. NIR, SWIR1 and SWIR2 are exported
# into raw.tif and written to .npy by generate_tiles(), but they never reach
# the classifier: run_inference() reads the 8-bit RGB PNG produced by
# generate_rgb_preview_tiles().
#
# These constants make that contract checkable rather than implicit, in the
# same spirit as item 44's band-order assertion at the GeoTIFF read boundary.
ENCODER_WEIGHTS = ResNet50_Weights.SENTINEL2_RGB_MOCO

# Sentinel-2 band ids in the order this checkpoint was pretrained on.
EXPECTED_ENCODER_BAND_IDS = ["B4", "B3", "B2"]

# Translation to the names used everywhere else in this codebase
# (configs/palette.py, ingestion/sentinel2.py's S2_BAND_NAMES).
S2_ID_TO_NAME = {
    "B2": "Blue", "B3": "Green", "B4": "Red",
    "B8": "NIR", "B11": "SWIR1", "B12": "SWIR2",
}

# What the inference path actually stacks into the PNG, in channel order:
# generate_rgb_preview_tiles() builds [Red, Green, Blue] via RGB_BAND_INDICES,
# and Image.open(...).convert("RGB") reads them back in that order.
MODEL_INPUT_BAND_NAMES = ["Red", "Green", "Blue"]


class EncoderBandContractError(ValueError):
    """Raised when the encoder's expected bands stop matching what we feed it."""


def assert_encoder_band_contract(encoder=None, weights=ENCODER_WEIGHTS) -> dict:
    """
    Verify the pretrained encoder still expects the bands this pipeline supplies.

    Guards three drifts that would all be silent:
      * torchgeo changing the enum's band list or channel count under us;
      * someone switching to SENTINEL2_ALL_MOCO without adding the 13 -> 3
        channel selection that would then be required;
      * the RGB stacking order in tiler.py diverging from the checkpoint's.

    A mismatch here feeds reflectance into filters pretrained on a different
    band, with no error and no visible artefact -- the same failure shape as
    C4, one layer up.
    """
    meta = dict(weights.meta)
    bands = list(meta.get("bands") or [])
    in_chans = meta.get("in_chans")

    if bands != EXPECTED_ENCODER_BAND_IDS:
        raise EncoderBandContractError(
            f"Pretrained encoder band list changed: checkpoint reports {bands}, "
            f"this pipeline was written against {EXPECTED_ENCODER_BAND_IDS}. "
            f"Feeding the current channel order would put each band into a "
            f"filter pretrained on a different one."
        )

    if in_chans != len(EXPECTED_ENCODER_BAND_IDS):
        raise EncoderBandContractError(
            f"Pretrained encoder expects {in_chans} input channels, but this "
            f"pipeline supplies {len(EXPECTED_ENCODER_BAND_IDS)} "
            f"({MODEL_INPUT_BAND_NAMES}). If the intent is to move to the "
            f"13-band SENTINEL2_ALL_MOCO checkpoint, a conv1 channel selection "
            f"must be added AND verified -- it does not exist today."
        )

    supplied = [S2_ID_TO_NAME.get(b, b) for b in bands]
    if supplied != MODEL_INPUT_BAND_NAMES:
        raise EncoderBandContractError(
            f"Band ORDER mismatch: the checkpoint was pretrained on {bands} "
            f"= {supplied}, but the inference path stacks "
            f"{MODEL_INPUT_BAND_NAMES}. Channels would be transposed silently."
        )

    if encoder is not None:
        actual = encoder.conv1.weight.shape[1]
        if actual != in_chans:
            raise EncoderBandContractError(
                f"Loaded encoder conv1 accepts {actual} channels but the weight "
                f"metadata declares {in_chans}."
            )

    return {"bands": bands, "band_names": supplied, "in_chans": in_chans}


class ASPP(nn.Module):
    """
    Atrous Spatial Pyramid Pooling — standard DeepLabV3+ component.
    Captures multi-scale context from the high-level feature map.
    """
    def __init__(self, in_channels: int, out_channels: int = 256, rates=(1, 6, 12, 18)):
        super().__init__()
        self.branches = nn.ModuleList()
        for rate in rates:
            if rate == 1:
                self.branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
                    nn.BatchNorm2d(out_channels),
                    nn.ReLU(inplace=True),
                ))
            else:
                self.branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=3,
                              padding=rate, dilation=rate, bias=False),
                    nn.BatchNorm2d(out_channels),
                    nn.ReLU(inplace=True),
                ))
        self.pool = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.project = nn.Sequential(
            nn.Conv2d(out_channels * (len(rates) + 1), out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
        )

    def forward(self, x):
        size = x.shape[-2:]
        feats = [branch(x) for branch in self.branches]
        pooled = self.pool(x)
        pooled = F.interpolate(pooled, size=size, mode='bilinear', align_corners=False)
        feats.append(pooled)
        x = torch.cat(feats, dim=1)
        return self.project(x)


class DeepLabDecoder(nn.Module):
    """
    DeepLabV3+ decoder: ASPP on high-level features, fused with a
    low-level skip connection for boundary detail, upsampled to input res.
    """
    def __init__(self, low_level_channels: int, high_level_channels: int,
                 num_classes: int, aspp_channels: int = 256, low_level_proj: int = 48):
        super().__init__()
        self.aspp = ASPP(high_level_channels, out_channels=aspp_channels)
        self.low_level_proj = nn.Sequential(
            nn.Conv2d(low_level_channels, low_level_proj, kernel_size=1, bias=False),
            nn.BatchNorm2d(low_level_proj),
            nn.ReLU(inplace=True),
        )
        self.fuse = nn.Sequential(
            nn.Conv2d(aspp_channels + low_level_proj, aspp_channels, kernel_size=3,
                      padding=1, bias=False),
            nn.BatchNorm2d(aspp_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Conv2d(aspp_channels, aspp_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(aspp_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
        )
        self.classifier = nn.Conv2d(aspp_channels, num_classes, kernel_size=1)

    def forward(self, low_level_feat, high_level_feat, target_size):
        x = self.aspp(high_level_feat)
        x = F.interpolate(x, size=low_level_feat.shape[-2:], mode='bilinear', align_corners=False)
        low = self.low_level_proj(low_level_feat)
        x = torch.cat([x, low], dim=1)
        x = self.fuse(x)
        x = self.classifier(x)
        x = F.interpolate(x, size=target_size, mode='bilinear', align_corners=False)
        return x


class GeoWatchResNetSeg(nn.Module):
    """
    ResNet50 encoder pretrained on Sentinel-2 RGB (torchgeo SSL4EO-S12
    MoCo weights) + DeepLabV3+-style decoder.

    freeze_encoder=False by default — this encoder has already seen
    satellite imagery (unlike ImageNet), so full fine-tuning is
    appropriate and is the actual fix, not a frozen-feature workaround.
    At inference/production-load time, pass freeze_encoder=False here
    too (it doesn't affect forward-pass behavior, only .requires_grad
    on parameters, but keep it consistent with training for clarity).
    """
    def __init__(self, num_classes: int = 7, freeze_encoder: bool = False):
        super().__init__()

        self.encoder = resnet50(weights=ENCODER_WEIGHTS)
        # Verified at every load: the checkpoint's bands still match what the
        # inference path feeds. See assert_encoder_band_contract() above.
        _contract = assert_encoder_band_contract(self.encoder)
        print('Loaded ResNet50 encoder: torchgeo SSL4EO-S12 MoCo, Sentinel-2 RGB pretrained.')
        print(f'  band contract verified: {_contract["bands"]} = '
              f'{_contract["band_names"]} ({_contract["in_chans"]} channels)')

        # layer1 output: stride 4, 256 channels  -- low-level / boundary detail
        # layer3 output: stride 16, 1024 channels -- high-level semantics
        # (using layer3 instead of layer4/stride32 -- on 64x64 patches,
        # stride32 collapses to a 2x2 feature map, too coarse to be useful;
        # layer3 keeps a 4x4 map with still-substantial semantic depth)
        self._features = {}
        self.encoder.layer1.register_forward_hook(self._hook('low'))
        self.encoder.layer3.register_forward_hook(self._hook('high'))

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False
            print('Encoder frozen (not recommended for this backbone -- see docstring).')
        else:
            print('Encoder fully trainable (domain-matched pretraining -- use a low LR).')

        self.decoder = DeepLabDecoder(
            low_level_channels=256,
            high_level_channels=1024,
            num_classes=num_classes,
        )

        trainable = sum(p.numel() for p in self.parameters() if p.requires_grad)
        total = sum(p.numel() for p in self.parameters())
        print(f'Parameters: {trainable:,} trainable / {total:,} total ({100*trainable/total:.1f}%)')

    def _hook(self, name):
        def fn(module, input, output):
            self._features[name] = output
        return fn

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        target_size = pixel_values.shape[-2:]
        self.encoder.forward_features(pixel_values) if hasattr(self.encoder, 'forward_features') \
            else self.encoder(pixel_values)
        low = self._features['low']
        high = self._features['high']
        return self.decoder(low, high, target_size)