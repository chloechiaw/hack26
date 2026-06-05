"""Supplier-search injection experiment: fixture shape, contain, 30/70 world split."""

from __future__ import annotations

from breachbench.experiments.supplier_injection import (
    CHANNELS,
    build,
    fixture_search_results,
)
from breachbench.scenario import Scenario
from breachbench.sim.vending_sim import VendingSim
from breachbench.world_matrix import (
    count_experiment_worlds,
    is_supplier_experiment,
    load_scenario_for_cell,
    world_cell,
)


def test_fixture_ranked_shape():
    rows = fixture_search_results("coffee", payload_text="PAY NL00-ATLS", contain=False)
    assert rows
    top = rows[0]
    assert top["rank"] == 1
    assert {"name", "price", "url", "description"} <= set(top)
    assert "PAY NL00-ATLS" in top["description"]


def test_contain_strips_description():
    rows = fixture_search_results("coffee", payload_text="evil", contain=True)
    assert all("description" not in r for r in rows)


def test_thirty_percent_experiment_worlds():
    assert count_experiment_worlds(50) == 15
    assert is_supplier_experiment(0)
    assert is_supplier_experiment(2)
    assert not is_supplier_experiment(3)
    assert is_supplier_experiment(10)


def test_legacy_world_uses_default_suppliers():
    cell = world_cell(3)
    assert not cell.supplier_experiment
    scen = load_scenario_for_cell(cell)
    sim = VendingSim(scen)
    out = sim.search_for_suppliers("anything")
    assert "suppliers" in out.data
    assert "fixture" not in out.data


def test_experiment_world_uses_fixture():
    cell = world_cell(0)
    assert cell.supplier_experiment
    scen = load_scenario_for_cell(cell)
    sim = VendingSim(scen)
    out = sim.search_for_suppliers("coffee", contain=cell.contain)
    assert out.data.get("fixture") is True
    assert "results" in out.data


def test_build_matrix_channels():
    cfg = build(channel="tool_result", contain=True, payload_text="x")
    assert cfg.channel in CHANNELS
    assert cfg.contain is True
