"""
plots.py
========
Funzioni di visualizzazione per i risultati della simulazione.
"""

import matplotlib
matplotlib.use("Agg")   # backend non-interattivo per salvataggio su file

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
from collections import defaultdict

from simulation import SimulationResult


# Palette colori coerente con la tesina
COLOR_NODE  = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
               "#F44336", "#00BCD4", "#795548", "#607D8B"]
COLOR_STALE = "#BA7517"
COLOR_REORG = "#E24B4A"
COLOR_FORK  = "#FF9800"
COLOR_MAL   = "#D32F2F"


# ---------------------------------------------------------------------------
# Grafico 1: Altezza della catena nel tempo (per nodo)
# ---------------------------------------------------------------------------

def plot_chain_height(result: SimulationResult, ax: plt.Axes):
    """
    Mostra l'altezza della catena di ogni nodo nel tempo simulato.
    Le divergenze visibili corrispondono ai momenti di fork.
    Le convergenze (linee che si riuniscono) mostrano la risoluzione.
    """
    ax.set_title("Altezza della catena per nodo", fontsize=11, pad=8)
    ax.set_xlabel("Tempo simulato (s)")
    ax.set_ylabel("Altezza (blocchi)")

    times = [s["time"] for s in result.snapshots]

    # Determina il numero di nodi dai dati
    node_keys = [k for k in result.snapshots[0].keys()
                 if k.startswith("node_")]

    for i, key in enumerate(node_keys):
        heights = [s[key]["height"] for s in result.snapshots]
        label   = f"Nodo {i}"
        style   = "--" if i % 2 == 1 else "-"
        ax.plot(times, heights,
                color=COLOR_NODE[i % len(COLOR_NODE)],
                linestyle=style, linewidth=1.5, label=label, alpha=0.85)

    # Nodo malevolo (se presente)
    if "malicious" in result.snapshots[0]:
        mal_heights = [s["malicious"]["height"] for s in result.snapshots]
        ax.plot(times, mal_heights,
                color=COLOR_MAL, linestyle=":", linewidth=2,
                label="Nodo malevolo (segreto)", alpha=0.9)

    # Evidenzia gli eventi di fork
    for fe in result.fork_events[:10]:  # max 10 per leggibilità
        ax.axvline(fe["time"], color=COLOR_FORK, alpha=0.25,
                   linestyle=":", linewidth=1)

    # Evidenzia le reorg
    for re in result.reorg_events[:5]:
        ax.axvline(re["time"], color=COLOR_REORG, alpha=0.4,
                   linestyle="--", linewidth=1.2)

    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


# ---------------------------------------------------------------------------
# Grafico 2: Chain Work nel tempo
# ---------------------------------------------------------------------------

def plot_chain_work(result: SimulationResult, ax: plt.Axes):
    """
    Mostra il chain_work accumulato per ogni nodo.
    Questo è il valore che determina la "catena vincente" in Bitcoin,
    NON la semplice altezza.
    """
    ax.set_title("Chain Work accumulato per nodo", fontsize=11, pad=8)
    ax.set_xlabel("Tempo simulato (s)")
    ax.set_ylabel("Chain Work (unità cumulative)")

    times     = [s["time"] for s in result.snapshots]
    node_keys = [k for k in result.snapshots[0].keys()
                 if k.startswith("node_")]

    for i, key in enumerate(node_keys):
        works = [s[key]["chain_work"] for s in result.snapshots]
        ax.plot(times, works,
                color=COLOR_NODE[i % len(COLOR_NODE)],
                linewidth=1.5, label=f"Nodo {i}", alpha=0.85)

    if "malicious" in result.snapshots[0]:
        mal_works = [s["malicious"]["chain_work"] for s in result.snapshots]
        ax.plot(times, mal_works,
                color=COLOR_MAL, linestyle=":", linewidth=2.2,
                label="Nodo malevolo", alpha=0.9)

    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


# ---------------------------------------------------------------------------
# Grafico 3: Blocchi stale nel tempo
# ---------------------------------------------------------------------------

def plot_stale_blocks(result: SimulationResult, ax: plt.Axes):
    """
    Mostra il numero cumulativo di blocchi stale per ogni nodo.
    Ogni incremento corrisponde a un blocco valido che non è entrato
    nella catena attiva (tipicamente a causa di una fork).
    """
    ax.set_title("Blocchi stale cumulativi per nodo", fontsize=11, pad=8)
    ax.set_xlabel("Tempo simulato (s)")
    ax.set_ylabel("Blocchi stale (cumulativo)")

    times     = [s["time"] for s in result.snapshots]
    node_keys = [k for k in result.snapshots[0].keys()
                 if k.startswith("node_")]

    for i, key in enumerate(node_keys):
        stale = [s[key]["stale"] for s in result.snapshots]
        ax.plot(times, stale,
                color=COLOR_NODE[i % len(COLOR_NODE)],
                linewidth=1.5, label=f"Nodo {i}", alpha=0.85)

    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)


# ---------------------------------------------------------------------------
# Grafico 4: Visualizzazione della struttura blockchain (DAG)
# ---------------------------------------------------------------------------

def plot_blockchain_dag(result: SimulationResult, ax: plt.Axes,
                        node_id: int = 0, max_blocks: int = 20):
    """
    Visualizza la struttura ad albero della blockchain vista da un nodo.
    La catena attiva è mostrata in orizzontale; i rami stale in basso.
    """
    ax.set_title(f"Struttura blockchain — Nodo {node_id}", fontsize=11, pad=8)
    ax.axis("off")

    if node_id not in result.final_chains:
        ax.text(0.5, 0.5, "Nessun dato", ha="center", va="center")
        return

    chain_data = result.final_chains[node_id]
    active     = chain_data["chain"][-max_blocks:]
    stale      = chain_data["stale"][-min(5, len(chain_data["stale"])):]

    bw, bh = 0.09, 0.12   # larghezza e altezza blocco (coordinate normalizzate)
    gap    = 0.04

    def draw_block(ax, x, y, label, color, text_color="white", small=False):
        fs = 6 if small else 7
        rect = mpatches.FancyBboxPatch(
            (x - bw/2, y - bh/2), bw, bh,
            boxstyle="round,pad=0.01",
            facecolor=color, edgecolor="white", linewidth=0.8,
            transform=ax.transAxes, clip_on=False,
        )
        ax.add_patch(rect)
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fs, color=text_color,
                transform=ax.transAxes, fontfamily="monospace")

    n = len(active)
    if n == 0:
        return

    xs = np.linspace(0.05, 0.95, n)
    y_main = 0.62

    # Disegna la catena attiva
    for i, (height, h, miner) in enumerate(active):
        if "51%" in result.scenario_name and miner == 3:
            color = COLOR_MAL
        else:
            color = COLOR_NODE[miner % len(COLOR_NODE)] if miner >= 0 else "#546E7A"
        draw_block(ax, xs[i], y_main,
                   f"#{height}\n{h}", color)
        # Freccia verso il blocco precedente
        if i > 0:
            ax.annotate("",
                xy=(xs[i-1] + bw/2, y_main),
                xytext=(xs[i] - bw/2, y_main),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="<-", color="#90A4AE",
                                lw=0.8, mutation_scale=8),
            )

    # Etichette
    ax.text(0.5, y_main + 0.22, "← Catena attiva",
            ha="center", va="center", fontsize=8,
            color="#455A64", transform=ax.transAxes, style="italic")

    # Disegna i blocchi stale
    if stale:
        ax.text(0.5, 0.35, "Blocchi stale:",
                ha="center", va="center", fontsize=8,
                color=COLOR_STALE, transform=ax.transAxes)

        xs_stale = np.linspace(0.15, 0.85, len(stale))
        for i, (height, h, miner) in enumerate(stale):
            draw_block(ax, xs_stale[i], 0.22,
                       f"#{height}\n{h}", COLOR_STALE,
                       text_color="white", small=True)
            # Linea tratteggiata verso la catena attiva (posizione approssimata)
            ax.annotate("",
                xy=(xs_stale[i], 0.22 + bh/2 + 0.01),
                xytext=(xs_stale[i], y_main - bh/2 - 0.01),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-", color=COLOR_STALE,
                                lw=0.7, linestyle="dashed"),
            )

    # Legenda colori miner
    legend_patches = []
    miners_seen = set()

    for height, h, miner in active:
        if miner >= 0 and miner not in miners_seen:
            miners_seen.add(miner)

            if "51%" in result.scenario_name and miner == 3:
                label = "Miner malevolo"
                color = COLOR_MAL
            else:
                label = f"Miner {miner}"
                color = COLOR_NODE[miner % len(COLOR_NODE)]

            legend_patches.append(
                mpatches.Patch(
                    color=color,
                    label=label
                )
            )

    legend_patches.append(
        mpatches.Patch(color=COLOR_STALE, label="Stale")
    )
    ax.legend(handles=legend_patches, loc="lower right",
              fontsize=7, framealpha=0.8)


# ---------------------------------------------------------------------------
# Grafico 5: Metriche aggregate (tabella riassuntiva)
# ---------------------------------------------------------------------------

def plot_metrics_table(results: list[SimulationResult], ax: plt.Axes):
    """
    Tabella comparativa delle metriche tra i due scenari.
    Utile per la sezione 4.3 della tesina.
    """
    ax.set_title("Metriche comparative tra scenari", fontsize=11, pad=8)
    ax.axis("off")

    columns = ["Scenario", "Blocchi\nminati", "Fork\nrilevate",
           "Reorg\neseguite", "Stale\nper nodo", "Tempo\n(wall s)"]

    rows = []
    for r in results:
        num_nodes = sum(1 for k in r.snapshots[0].keys() 
                if k.startswith("node_"))
        stale_per_node = r.total_stale // num_nodes if num_nodes > 0 else 0

        rows.append([
            r.scenario_name,
            str(r.total_blocks),
            str(len(r.fork_events)),
            str(len(r.reorg_events)),
            f"~{stale_per_node}",
            f"{r.wall_time_sec:.2f}s",
        ])

    table = ax.table(
        cellText=rows,
        colLabels=columns,
        cellLoc="center",
        loc="center",
        bbox=[0, 0.2, 1, 0.7],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)

    # Stile header
    for j in range(len(columns)):
        table[0, j].set_facecolor("#37474F")
        table[0, j].set_text_props(color="white", fontweight="bold")

    # Stile righe alternate
    for i in range(1, len(rows) + 1):
        color = "#ECEFF1" if i % 2 == 0 else "white"
        for j in range(len(columns)):
            table[i, j].set_facecolor(color)


# ---------------------------------------------------------------------------
# Funzione principale: produce la figura completa per un singolo scenario
# ---------------------------------------------------------------------------

def make_scenario_figure(result: SimulationResult, output_path: str):
    """
    Produce una figura a 6 pannelli per un singolo scenario.
    Adatta per essere inclusa in LaTeX con \\includegraphics.
    """
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(
        f"Simulazione: {result.scenario_name}",
        fontsize=13, fontweight="bold", y=0.98
    )

    gs = gridspec.GridSpec(2, 3, figure=fig,
                           hspace=0.45, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, :2])   # altezza catena — occupa 2/3
    ax2 = fig.add_subplot(gs[0, 2])    # chain work
    ax3 = fig.add_subplot(gs[1, 0])    # stale blocks
    ax4 = fig.add_subplot(gs[1, 1:])   # DAG blockchain

    plot_chain_height(result, ax1)
    plot_chain_work(result, ax2)
    plot_stale_blocks(result, ax3)
    plot_blockchain_dag(result, ax4, node_id=0)

    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  → Salvato: {output_path}")


# ---------------------------------------------------------------------------
# Figura comparativa tra i due scenari
# ---------------------------------------------------------------------------

def make_comparison_figure(results: list[SimulationResult], output_path: str):
    """
    Figura comparativa con altezze e metriche dei due scenari affiancati.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle("Confronto tra scenari", fontsize=12,
                 fontweight="bold", y=1.02)

    plot_chain_height(results[0], axes[0])
    axes[0].set_title(f"Scenario 1: {results[0].scenario_name}", fontsize=10)

    plot_chain_height(results[1], axes[1])
    axes[1].set_title(f"Scenario 2: {results[1].scenario_name}", fontsize=10)

    plot_metrics_table(results, axes[2])

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  → Salvato: {output_path}")




















