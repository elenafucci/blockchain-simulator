"""
main.py
=======
Punto di ingresso del simulatore.
Esegue i due scenari descritti nel Capitolo 4.3 della tesina:

  Scenario 1 — Fork competitivo
    Quattro miner con pari hash power trovano quasi simultaneamente un blocco.
    Si osserva come la rete converge sulla catena con più chain_work.

  Scenario 2 — Attacco di riorganizzazione (51% attack simulation)
    Un nodo malevolo con hash power maggioritario mina in segreto
    una catena alternativa più lunga, poi la rivela.
    Si osservano le reorg forzate sui nodi onesti.
"""

import os
import sys
import json
import random

# Riproducibilità degli esperimenti
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

from simulation import Simulator
from plots import make_scenario_figure, make_comparison_figure


# ---------------------------------------------------------------------------
# Configurazione output
# ---------------------------------------------------------------------------

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Scenario 1: Fork competitivo
# ---------------------------------------------------------------------------

def run_scenario_1() -> object:
    """
    Scenario 1 — Fork competitivo tra quattro miner con pari potenza.

    Configurazione:
        - 4 nodi equipotenti con hash power normalizzato hi = 0.25;
        - latenza media di propagazione pari a 800 ms;
        - difficulty fissata a 3 zeri esadecimali;
        - block time atteso di 20 secondi simulati;
        - durata complessiva della simulazione di 3600 secondi, 
            corrispondente a circa 180 block time teorici attesi.

    Cosa osservare:
        - Divergenze temporanee tra i tip dei nodi dovute alle fork.
        - Riconvergenza spontanea tramite la most-work chain rule.
        - Accumulo di blocchi stale nei rami esclusi dalla catena finale.
            """
    print("\n" + "="*60)
    print("SCENARIO 1: Fork competitivo")
    print("="*60)
    print("  Nodi: 4")
    print("  Hash power: [0.25, 0.25, 0.25, 0.25]")
    print("  Latenza: 800 ms")
    print("  Difficulty: 3")
    print("  Block time: 20 s")
    print("  Durata: 3600 s simulati")
    print()

    sim = Simulator(
        num_nodes   = 4,
        hash_powers = [0.25, 0.25, 0.25, 0.25],
        latency_ms  = 800,
        difficulty  = 3,
        block_time  = 20,
    )

    result = sim.run(
        duration      = 3600,
        scenario_name = "Fork Competitivo",
        dt            = 0.5,
    )

    # Stampa riepilogo testuale
    print(f"  Blocchi minati:   {result.total_blocks}")
    print(f"  Fork rilevate:    {len(result.fork_events)}")
    print(f"  Reorg eseguite:   {len(result.reorg_events)}")
    print(f"  Blocchi stale:    {result.total_stale}")
    print(f"  Tempo wall:       {result.wall_time_sec:.2f}s")

    if result.reorg_events:
        print("\n  Dettaglio reorg:")
        for r in result.reorg_events[:5]:
            print(f"    t={r['time']:.1f}s  Nodo {r['node']}  {r['detail']}")

    if result.fork_events:
        print("\n  Prime fork rilevate:")
        for f in result.fork_events[:3]:
            tips = ", ".join(f"N{k}={v[:6]}"
                             for k, v in f["tips"].items())
            print(f"    t={f['time']:.1f}s  →  {tips}")

    # Salva grafico
    path = os.path.join(OUTPUT_DIR, "scenario1_fork_competitivo.png")
    make_scenario_figure(result, path)

    # Salva log JSON (utile per analisi ulteriori nella tesina)
    log_path = os.path.join(OUTPUT_DIR, "scenario1_log.json")
    with open(log_path, "w") as f:
        json.dump({
            "config": {
                "num_nodes": 4,
                "hash_powers": [0.25, 0.25, 0.25, 0.25],
                "latency_ms": 800,
                "difficulty": 3,
                "block_time": 20,
                "duration": 3600,
                "random_seed": RANDOM_SEED,
            },
            "metrics": {
                "total_blocks":    result.total_blocks,
                "fork_events":     len(result.fork_events),
                "reorg_events":    len(result.reorg_events),
                "total_stale":     result.total_stale,
                "wall_time_sec":   result.wall_time_sec,
            },
            "fork_events":  result.fork_events[:20],
            "reorg_events": result.reorg_events[:20],
        }, f, indent=2)
    print(f"  → Log JSON: {log_path}")

    # Verifica consenso finale 
    tips = {n.tip.hash for n in sim.nodes} 
    print(f"\n Consenso finale raggiunto: {len(tips) == 1}")
    print(f" Tip unici: {len(tips)} → {[t[:8] for t in tips]}") 
    return result


# ---------------------------------------------------------------------------
# Scenario 2: Attacco di riorganizzazione (51%)
# ---------------------------------------------------------------------------

def run_scenario_2() -> object:
    """
    Scenario 2 — Attacco del 51% con catena segreta.
    Configurazione:
        - 3 nodi onesti con hash power totale = 3.0
        - 1 nodo malevolo con hash power = 4.0 (57%)
        - Il nodo malevolo mina in segreto fino a t=1200s
        - A t=1200s rivela la catena privata
        - I nodi onesti adottano la catena con chain work maggiore

    Cosa osservare:
        - La catena onesta cresce normalmente fino alla rivelazione
        - A t=1200s la catena privata viene pubblicata
        - I nodi onesti possono eseguire una riorganizzazione profonda
            se la catena privata accumula più chain work
        - Il chain work della catena malevola supera quello della catena onesta
        - Il comportamento osservato riproduce qualitativamente l'attacco del 51%
            descritto da Satoshi Nakamoto nella Sezione 11 del white paper Bitcoin
    """

    print("\n" + "="*60)
    print("SCENARIO 2: Attacco del 51% (catena segreta)")
    print("="*60)
    print("  Nodi onesti: 3 (hp=1.0 ciascuno)")
    print("  Nodo malevolo: 1 (hp=4.0 → 57% dell'hash power totale)")
    print("  Latenza: 2000 ms")
    print("  Block time: 10 s")
    print("  Difficulty: 3")
    print("  Rivelazione catena segreta: t=1200 s")
    print("  Durata: 2000 s simulati")
    print()

    # Nota: reimpostiamo il seed per avere risultati riproducibili
    # indipendentemente dall'ordine di esecuzione degli scenari
    random.seed(RANDOM_SEED + 1)

    sim = Simulator(
        num_nodes           = 3,
        hash_powers         = [1.0, 1.0, 1.0],
        latency_ms          = 2000,
        difficulty          = 3,
        block_time          = 10,
        malicious_node      = 4.0,
        malicious_reveal_at = 1200.0,
    )

    result = sim.run(
        duration      = 2000,
        scenario_name = "Attacco 51% (catena segreta)",
        dt            = 0.5,
    )

    print(f"  Blocchi minati totali: {result.total_blocks}")
    print(f"  Fork rilevate:         {len(result.fork_events)}")
    print(f"  Reorg eseguite:        {len(result.reorg_events)}")
    print(f"  Blocchi stale:         {result.total_stale}")
    print(f"  Tempo wall:            {result.wall_time_sec:.2f}s")

    # Evidenzia le reorg da attacco (taggate con ":ATTACK" dal _reveal_malicious_chain)
    attack_reorgs = [r for r in result.reorg_events if "ATTACK" in r.get("detail", "")]
    if attack_reorgs:
        print(f"\n  Reorg da attacco: {len(attack_reorgs)}")
        for r in attack_reorgs[:5]:
            print(f"    t={r['time']:.1f}s  Nodo {r['node']}  {r['detail']}")
    else:
        print("\n  (Nessuna reorg da attacco: il nodo malevolo non aveva")
        print("   abbastanza chain_work al momento della rivelazione.)")
        print("   Prova ad aumentare malicious_node o malicious_reveal_at.")

    path = os.path.join(OUTPUT_DIR, "scenario2_attacco_51.png")
    make_scenario_figure(result, path)

    log_path = os.path.join(OUTPUT_DIR, "scenario2_log.json")
    with open(log_path, "w") as f:
        json.dump({
            "config": {
                "num_nodes": 3,
                "hash_powers": [1.0, 1.0, 1.0],
                "malicious_hash_power": 4.0,
                "malicious_reveal_at": 1200.0,
                "latency_ms": 2000,
                "difficulty": 3,
                "block_time": 10,
                "duration": 2000,
                "random_seed": RANDOM_SEED + 1,
            },
            "metrics": {
                "total_blocks":    result.total_blocks,
                "fork_events":     len(result.fork_events),
                "reorg_events":    len(result.reorg_events),
                "attack_reorgs":   len(attack_reorgs),
                "total_stale":     result.total_stale,
                "wall_time_sec":   result.wall_time_sec,
            },
            "reorg_events": result.reorg_events[:20],
        }, f, indent=2)
    print(f"  → Log JSON: {log_path}")

    # Verifica consenso finale (solo nodi onesti)
    tips = {n.tip.hash for n in sim.nodes}
    print(f"\n  Consenso finale nodi onesti: {len(tips) == 1}")
    print(f"  Tip unici: {len(tips)} → {[t[:8] for t in tips]}")

    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════╗")
    print("║  Simulatore di Convergenza della Blockchain      ║")
    print("║  Bitcoin — Tesina di Crittografia                ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"\nRandom seed: {RANDOM_SEED}  (per riproducibilità)")
    print(f"Output directory: ./{OUTPUT_DIR}/")

    result1 = run_scenario_1()
    result2 = run_scenario_2()

    # Figura comparativa tra i due scenari
    print("\n  Generazione figura comparativa...")
    make_comparison_figure(
        [result1, result2],
        os.path.join(OUTPUT_DIR, "confronto_scenari.png")
    )

    print("\n" + "="*60)
    print("Simulazione completata.")
    print(f"File generati in ./{OUTPUT_DIR}/:")
    for fname in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, fname))
        print(f"  {fname:45s}  ({size:,} bytes)")
    print("="*60)