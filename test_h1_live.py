"""Live panels for a 1-channel headset must not use the 14-site EPOC indexes."""

from __future__ import annotations

import math

import numpy as np

from sevenbeing.brain.bci.gui.server import BleWorker
from sevenbeing.brain.bci.pipeline.affect import AffectMeter
from sevenbeing.brain.bci.pipeline.contact import ContactProxy
from sevenbeing.brain.bci.pipeline.face import FaceMeter


def test_one_channel_affect_stays_in_range_and_interest_is_neutral() -> None:
    meter = AffectMeter(32, n_ch=1)
    scores = None
    for i in range(80):
        scores = meter.push([100.0 + 10.0 * math.sin(i / 3.0)])
    assert scores is not None
    assert len(scores) == 6
    assert all(0.0 <= value <= 1.0 for value in scores)
    assert abs(scores[4] - 0.5) < 1e-6
    assert meter.channel_bands is not None
    assert len(meter.channel_bands) == 1
    assert meter.bands is not None and len(meter.bands) == 5


def test_short_row_does_not_index_missing_electrodes() -> None:
    meter = AffectMeter(128, n_ch=1)
    stacked = np.arange(1, 6, dtype=float).reshape(5, 1)
    scores = meter._scores_from_power(stacked)
    assert scores[4] == 0.5
    assert len(meter.channel_bands) == 1


def test_fourteen_channel_interest_still_uses_asymmetry() -> None:
    meter = AffectMeter(128, n_ch=14)
    stacked = np.ones((5, 14), dtype=float)
    stacked[1, 0] = 1.0
    stacked[1, 13] = 20.0
    scores = meter._scores_from_power(stacked)
    assert scores[4] > 0.9
    assert len(meter.channel_bands) == 14
    assert meter.push([1.0]) is None


def test_forehead_blink_and_hidden_lateral_actions() -> None:
    meter = FaceMeter(250, n_ch=1)
    assert meter.lateral is False
    out = [0.0, None, None, None, None]
    for _ in range(80):
        out = meter.push([300.0])
    assert out[0] == 0.0
    assert out[1:] == [None, None, None, None]
    spiked = meter.push([1200.0])
    assert spiked[0] == 1.0
    assert spiked[1] is None

    epoc = FaceMeter(128)
    assert epoc.lateral is True
    assert all(value == 0.0 for value in epoc.push([0.0] * 14))


def test_contact_rail_is_bad_and_quiet_fpz_is_good() -> None:
    proxy = ContactProxy(1, 250, 208_000.0)
    quiet = proxy.push([300.0])
    assert quiet[0] > 0.9
    rail = quiet
    for _ in range(40):
        rail = proxy.push([200_000.0])
    assert rail[0] < 0.2


def test_closed_channel_drops_out_of_affect() -> None:
    from sevenbeing.brain.bci.devices.montage import closed_indices

    assert closed_indices(14, [13, 13, -1, 20]) == (13,)
    try:
        closed_indices(1, [0])
    except ValueError:
        pass
    else:
        raise AssertionError("closing the only channel should fail")

    meter = AffectMeter(128, n_ch=14)
    meter.closed = (13,)
    stacked = np.ones((5, 14), dtype=float)
    stacked[1, 0] = 1.0
    stacked[1, 13] = 20.0
    scores = meter._scores_from_power(stacked)
    assert scores[4] == 0.5
    assert meter.channel_bands is not None
    assert meter.channel_bands[13] == [0.0, 0.0, 0.0, 0.0]
    assert meter.channel_bands[0] != [0.0, 0.0, 0.0, 0.0]


def test_full_scale_parses_h1_detail() -> None:
    assert BleWorker._scale_uv({"detail": "ble · ±208 mV · 250 sps"}) == 208_000.0
    assert BleWorker._scale_uv({"detail": "±2.5 V", "kind": "h1"}) == 2_500_000.0
    assert BleWorker._scale_uv({"kind": "h1"}) == 208_000.0
