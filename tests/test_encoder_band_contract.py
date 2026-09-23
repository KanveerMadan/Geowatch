r"""
Encoder band-contract tests — the 6-band/13-band mapping question.

THE VERIFICATION THAT PROMPTED THESE. The concern was that the production model
uses a 13-band SSL4EO checkpoint (ResNet50_Weights.SENTINEL2_ALL_MOCO) sliced
down to 6 input channels, and that the slice indices might select the wrong
bands — feeding SWIR into filters pretrained on cirrus, silently.

Measured: that is not what happens. The code loads SENTINEL2_RGB_MOCO, a THREE
-band checkpoint (in_chans=3, bands ['B4','B3','B2']). conv1.weight is
(64, 3, 7, 7) both freshly loaded and in the deployed production checkpoint
that produced the 0.313 LOCO baseline. No slicing code exists anywhere in the
repo. So there is no 13->6 mapping that could be off by one.

What the model actually sees is Red, Green, Blue — NIR, SWIR1 and SWIR2 are
exported and written to .npy, but never reach the classifier.

These tests pin that contract so it cannot drift, and so that a future move to
the 13-band checkpoint cannot happen without the channel selection it would
require.

Run:  pytest tests/test_encoder_band_contract.py
"""

import pytest
import torch

from ingestion.resnet_model import (
    ENCODER_WEIGHTS,
    EXPECTED_ENCODER_BAND_IDS,
    MODEL_INPUT_BAND_NAMES,
    EncoderBandContractError,
    assert_encoder_band_contract,
)


def test_checkpoint_is_the_three_band_rgb_one_not_the_13_band():
    meta = ENCODER_WEIGHTS.meta
    assert meta["in_chans"] == 3, (
        "the encoder is no longer 3-band; if this is now SENTINEL2_ALL_MOCO, a "
        "conv1 channel selection is required and must be verified"
    )
    assert list(meta["bands"]) == ["B4", "B3", "B2"]


def test_no_band_slicing_code_exists():
    """
    The premise under test was a 13->6 conv1 slice. Assert none exists.

    Parses the AST rather than grepping text: the 13-band checkpoint is named
    in a docstring and in an error message, both explaining why it is NOT used,
    and that prose should stay. Only real attribute access and real subscripting
    count as usage.
    """
    import ast

    from torchgeo.models import ResNet50_Weights

    assert ENCODER_WEIGHTS is ResNet50_Weights.SENTINEL2_RGB_MOCO, (
        "the encoder weights enum changed; a channel selection may now be needed"
    )

    tree = ast.parse(open("ingestion/resnet_model.py").read())
    used_enums, subscripted = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("SENTINEL2_"):
            used_enums.append(node.attr)
        # conv1.weight[...] -- a slice of the pretrained kernel
        if isinstance(node, ast.Subscript):
            tgt = node.value
            if (isinstance(tgt, ast.Attribute) and tgt.attr == "weight"
                    and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == "conv1"):
                subscripted.append(ast.dump(node)[:60])

    assert used_enums == ["SENTINEL2_RGB_MOCO"], (
        f"unexpected weight enums referenced in code: {used_enums}"
    )
    assert not subscripted, f"conv1 weights are being sliced: {subscripted}"


def test_band_order_matches_what_inference_feeds():
    """
    The checkpoint's ['B4','B3','B2'] must equal the [Red, Green, Blue] order
    that generate_rgb_preview_tiles stacks and Image.convert('RGB') reads back.
    """
    result = assert_encoder_band_contract()
    assert result["band_names"] == MODEL_INPUT_BAND_NAMES == ["Red", "Green", "Blue"]


def test_contract_holds_against_a_real_loaded_encoder():
    from torchgeo.models import resnet50
    enc = resnet50(weights=ENCODER_WEIGHTS)
    assert enc.conv1.weight.shape[1] == 3
    assert_encoder_band_contract(enc)


def test_deployed_checkpoint_is_three_channel():
    """The model that produced the 0.313 baseline, not just a fresh load."""
    import os
    path = "models/production/geowatch_production_model.pth"
    if not os.path.exists(path):
        pytest.skip("production checkpoint absent")
    ck = torch.load(path, map_location="cpu", weights_only=False)
    w = ck["model_state_dict"]
    key = next(k for k in w if k.endswith("conv1.weight"))
    assert tuple(w[key].shape) == (64, 3, 7, 7)


# ── The assertion must actually fire ──

class _FakeWeights:
    def __init__(self, bands, in_chans):
        self.meta = {"bands": bands, "in_chans": in_chans}


def test_changed_band_list_raises():
    with pytest.raises(EncoderBandContractError, match="band list changed"):
        assert_encoder_band_contract(weights=_FakeWeights(["B2", "B3", "B4"], 3))


def test_thirteen_band_checkpoint_raises_without_a_channel_selection():
    """
    The exact scenario the verification was worried about: swapping in the
    13-band checkpoint must not silently work.
    """
    bands13 = ["B1","B2","B3","B4","B5","B6","B7","B8","B8a","B9","B10","B11","B12"]
    with pytest.raises(EncoderBandContractError):
        assert_encoder_band_contract(weights=_FakeWeights(bands13, 13))


def test_channel_count_disagreeing_with_metadata_raises():
    class _Enc:
        class conv1:
            weight = torch.zeros(64, 6, 7, 7)
    with pytest.raises(EncoderBandContractError, match="conv1 accepts 6"):
        assert_encoder_band_contract(_Enc(), weights=_FakeWeights(["B4","B3","B2"], 3))
