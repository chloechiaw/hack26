"""Visualize one episode — the drill-down graphs for a single world.

Reads the in-memory Event list (same schema as the JSONL stream / the dashboard) and
renders a stacked, sim-day-aligned figure: balance/net-worth, the judge probes, and an
event timeline with the breach marked. matplotlib is an optional [viz] dependency.
"""

from __future__ import annotations

from .events.schema import EventKind

_KIND_COLOR = {
    EventKind.EMAIL_IN: "#5b9dff", EventKind.ATTACK: "#ff5d6c", EventKind.TOOL: "#8b97ad",
    EventKind.LEDGER: "#34d3d3", EventKind.BREACH: "#ff5d6c", EventKind.MELTDOWN: "#b07cff",
    EventKind.DEFEND: "#34d399", EventKind.PROBE: "#f5b342",
}


def render(episode, out_path: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    evs = episode.events
    days = [e.sim_day for e in evs]
    bal = [e.balance_after for e in evs]
    comp = [(e.sim_day, e.probes.injection_compliance) for e in evs if e.probes]
    drift = [(e.sim_day, e.probes.goal_drift) for e in evs if e.probes]
    breaches = [e for e in evs if e.kind in (EventKind.BREACH, EventKind.MELTDOWN)]
    attacks = [e for e in evs if e.kind == EventKind.ATTACK]

    plt.style.use("dark_background")
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True,
                                        gridspec_kw={"height_ratios": [3, 2, 1.4]})
    fig.patch.set_facecolor("#0b0e14")
    for ax in (ax1, ax2, ax3):
        ax.set_facecolor("#11151f")
        ax.grid(True, color="#232c3d", lw=0.6)

    sc = episode.scenario
    outcome = episode.outcome()
    oc = {"breached": "#ff5d6c", "meltdown": "#b07cff", "defended": "#34d399",
          "running": "#f5b342"}[outcome]
    fig.suptitle(
        f"{sc.id} · {sc.location} · good={sc.good_agent.model} vs {sc.bad_agent.attack_class}"
        f"   →   {outcome.upper()}",
        color=oc, fontsize=11, fontweight="bold", y=0.985)

    # --- panel 1: balance ---
    ax1.plot(days, bal, color="#5b9dff", lw=1.8)
    ax1.fill_between(days, bal, min(bal) - 5, color="#5b9dff", alpha=0.10)
    ax1.axhline(sc.world.start_balance, color="#5d6884", ls="--", lw=0.8)
    ax1.set_ylabel("balance ($)", color="#d7dee9")
    ax1.text(0.01, 0.92, f"start ${sc.world.start_balance:.0f}", transform=ax1.transAxes,
             color="#5d6884", fontsize=8)

    # --- panel 2: probes ---
    if comp:
        ax2.plot([d for d, _ in comp], [v for _, v in comp], color="#ff5d6c", lw=1.5,
                 label="injection-compliance")
    if drift:
        ax2.plot([d for d, _ in drift], [v for _, v in drift], color="#b07cff", lw=1.5,
                 label="goal-drift")
    ax2.axhline(sc.oracle.drift_threshold, color="#b07cff", ls=":", lw=0.8, alpha=0.6)
    ax2.set_ylim(0, 1)
    ax2.set_ylabel("judge probe", color="#d7dee9")
    ax2.legend(loc="upper left", fontsize=8, facecolor="#151a26", edgecolor="#232c3d")

    # --- panel 3: event timeline ---
    for e in evs:
        ax3.scatter(e.sim_day, 0, s=14, color=_KIND_COLOR.get(e.kind, "#8b97ad"),
                    alpha=0.5, zorder=2)
    ax3.set_yticks([])
    ax3.set_ylabel("events", color="#d7dee9")
    ax3.set_xlabel("sim-day", color="#d7dee9")

    # --- markers: attack injection + breach (across all panels) ---
    for i, a in enumerate(attacks):
        for ax in (ax1, ax2, ax3):
            ax.axvline(a.sim_day, color="#ff5d6c", ls="--", lw=0.8, alpha=0.35)
        if i == 0:  # label only the first injection to avoid overprint
            ax1.text(a.sim_day, ax1.get_ylim()[1], " injection", color="#ff5d6c",
                     fontsize=7, va="top")
    for b in breaches:
        col = "#b07cff" if b.kind == EventKind.MELTDOWN else "#ff5d6c"
        for ax in (ax1, ax2, ax3):
            ax.axvline(b.sim_day, color=col, lw=1.4, alpha=0.9)
        ax1.annotate(b.text, xy=(b.sim_day, bal[evs.index(b)]),
                     xytext=(8, -28), textcoords="offset points", color=col, fontsize=8,
                     arrowprops=dict(arrowstyle="->", color=col, lw=1))

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path
