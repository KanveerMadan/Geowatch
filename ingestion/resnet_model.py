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

        self.encoder = resnet50(weights=ResNet50_Weights.SENTINEL2_RGB_MOCO)
        print('Loaded ResNet50 encoder: torchgeo SSL4EO-S12 MoCo, Sentinel-2 RGB pretrained.')

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