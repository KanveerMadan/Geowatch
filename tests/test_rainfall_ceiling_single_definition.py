"""
Item 26, task 6: the 2,500 mm rainfall ceiling shared by flash flood and
waterlogging has one definition (docs/susceptibility_dag.md found two that
could drift apart silently).
"""
import ast
import pathlib

import configs.flash_flood_constants as ffc
import susceptibility.retired_methods.flash_flood_round2 as ff
import susceptibility.retired_methods.waterlogging_round2 as wl

CONFIGS = pathlib.Path(ffc.__file__).parent
NAME = "FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM"


def test_defined_once_across_configs():
    defs = [p.name for p in CONFIGS.glob("*.py")
            for node in ast.walk(ast.parse(p.read_text()))
            if isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) == NAME for t in node.targets)]
    assert defs == ["flash_flood_constants.py"], defs


def test_every_layer_reading_it_reads_the_same_object():
    # Item 26 Phase 1a: flash flood now reads an IMERG intensity, not the
    # annual total, so waterlogging is the one consumer left.
    assert getattr(wl, NAME) is getattr(ffc, NAME)
    assert not hasattr(ff, NAME)
