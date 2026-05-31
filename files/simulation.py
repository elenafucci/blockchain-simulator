"""
simulation.py
=============
Motore della simulazione a eventi discreti.

La simulazione avanza per "tick" di tempo simulato.
In ogni tick:
  1. Ogni nodo tenta di minare (probabilità poissoniana)
  2. I blocchi trovati vengono accodati nella rete con latenza
  3. I blocchi il cui arrivo è scaduto vengono consegnati e processati

Architettura:
  - Un blocco appena minato non viene inserito direttamente nella
    blockchain locale del miner.
  - Il blocco viene invece propagato tramite la stessa logica usata
    per tutti gli altri nodi (con latenza nulla verso il mittente).
  - In questo modo tutta la logica di validazione e aggiornamento
    della catena è centralizzata in add_block().
"""

import random
from dataclasses import dataclass, field
from typing import Optional
import time as wall_time

from blockchain import Block, make_genesis
from node import Node, NetworkEvent


@dataclass
class SimulationResult:
    scenario_name:     str
    snapshots:         list[dict] = field(default_factory=list)
    fork_events:       list[dict] = field(default_factory=list)
    reorg_events:      list[dict] = field(default_factory=list)
    convergence_times: list[float] = field(default_factory=list)
    total_blocks:      int   = 0
    total_stale:       int   = 0
    wall_time_sec:     float = 0.0
    final_chains:      dict  = field(default_factory=dict)


class Simulator:
    def __init__(
        self,
        num_nodes:           int,
        hash_powers:         list[float],
        latency_ms:          float = 200.0,
        difficulty:          int   = 3,
        block_time:          float = 60.0,
        malicious_node:      Optional[float] = None,
        malicious_reveal_at: Optional[float] = None,
    ):
        self.latency_ms          = latency_ms
        self.difficulty          = difficulty
        self.block_time          = block_time
        self.malicious_reveal_at = malicious_reveal_at
        self.genesis             = make_genesis(difficulty)

        # Nodi onesti
        self.nodes: list[Node] = [
            Node(i, hash_powers[i], self.genesis, difficulty)
            for i in range(num_nodes)
        ]

        # Nodo malevolo
        self.malicious: Optional[Node] = None
        if malicious_node is not None:
            self.malicious = Node(
                num_nodes, malicious_node, self.genesis,
                difficulty, is_malicious=True
            )

        self.network_queue: list[NetworkEvent] = []
        self.sim_time:    float = 0.0
        self.total_mined: int   = 0
        self.global_log:  list  = []

    # ------------------------------------------------------------------
    def run(self, duration: float, scenario_name: str = "sim",
            dt: float = 0.5) -> SimulationResult:
        result = SimulationResult(scenario_name=scenario_name)
        t0 = wall_time.time()

        # Fase 1: simulazione normale
        while self.sim_time < duration:
            self.sim_time += dt
            self._step(dt, result)
            result.snapshots.append(self._snapshot())

        # Fase 2: draining con latenza zero per convergenza naturale
        latency_originale = self.latency_ms
        self.latency_ms = 0.0
        drain_end = self.sim_time + 600.0
        while self.sim_time < drain_end:
            tips = {n.tip.hash for n in self.nodes}
            if len(tips) == 1:
                break
            self.sim_time += dt
            self._step(dt, result)
            result.snapshots.append(self._snapshot())
        self.latency_ms = latency_originale

        result.total_blocks  = self.total_mined
        result.total_stale   = sum(n.stale_count for n in self.nodes)
        result.wall_time_sec = wall_time.time() - t0
        result.final_chains  = self._final_chains()
        return result

    # ------------------------------------------------------------------
    def _step(self, dt: float, result: SimulationResult):
        """
        Un passo temporale:
        1. Ogni nodo tenta di minare con probabilità derivata dal modello
            di Poisson del mining Bitcoin
         2. I blocchi trovati entrano nella coda di rete
         3. La rete consegna i blocchi con ritardo
        """
        total_hp_honest = sum(n.hash_power for n in self.nodes)
        total_hp_all    = total_hp_honest + (
            self.malicious.hash_power if self.malicious else 0)

        # --- Mining onesti ---
        for node in self.nodes:
            p = (node.hash_power / total_hp_all) * (dt / self.block_time)
            if random.random() < p:
                block = self._do_mine(node)
                if block:
                    self.total_mined += 1
                    self._broadcast(block, sender_id=node.node_id,
                                    include_self=True, secret=False)

        # --- Mining malevolo ---
        if self.malicious:
            p = (self.malicious.hash_power / total_hp_all) * (dt / self.block_time)
            if random.random() < p:
                block = self._do_mine(self.malicious)
                if block:
                    self.total_mined += 1
                    # Mina in segreto: invia solo a se stesso
                    self._broadcast(block, sender_id=self.malicious.node_id,
                                    include_self=True, secret=True)

            # Rivela la catena al momento stabilito
            if (self.malicious_reveal_at is not None and
                    self.sim_time >= self.malicious_reveal_at):
                self._reveal_malicious_chain(result)

        # --- Consegna blocchi ---
        self._deliver_blocks(result)

    # ------------------------------------------------------------------
    def _do_mine(self, node: Node) -> Optional[Block]:
        """
        Esegue il mining senza modificare la catena del nodo.
        Restituisce il blocco trovato o None.
        """
        import hashlib
        tip = node.blockchain.tip

        tx_data     = f"tx_{tip.index+1}_n{node.node_id}_{self.sim_time}"
        merkle_root = hashlib.sha256(tx_data.encode()).hexdigest()[:16]

        candidate = Block(
            index=tip.index + 1,
            prev_hash=tip.hash,
            merkle_root=merkle_root,
            timestamp=self.sim_time,
            difficulty=self.difficulty,
            miner_id=node.node_id,
        )

        max_attempts = int(node.hash_power * 10000)

        for _ in range(max_attempts):
            candidate.nonce = random.randint(0, 2**32 - 1)
            candidate.hash  = candidate.compute_hash()
            if candidate.meets_target():
                # chain_work impostato qui per coerenza; verrà ricalcolato
                # in add_block dal padre effettivo nel DAG locale del nodo
                candidate.chain_work = tip.chain_work + self.difficulty
                return candidate

        return None

    # ------------------------------------------------------------------
    def _broadcast(self, block: Block, sender_id: int,
                   include_self: bool = False, secret: bool = False):
        """
        Accoda un blocco per la consegna.
        secret=True → invia solo al mittente (mining segreto).

        lat_sim è in secondi simulati: corrisponde direttamente al
        ritardo di propagazione nella timeline della simulazione.
        NON va moltiplicato per block_time (che è già in secondi simulati).
        """
        # FIX: lat_sim in secondi simulati, senza * block_time
        lat_sim = self.latency_ms / 1000.0

        all_nodes = list(self.nodes)
        if self.malicious:
            all_nodes.append(self.malicious)

        for node in all_nodes:
            if secret and node.node_id != sender_id:
                continue
            if not include_self and node.node_id == sender_id:
                continue
            delay = 0.0 if node.node_id == sender_id \
                        else lat_sim * (0.5 + random.random())
            self.network_queue.append(NetworkEvent(
                block=block,
                target_id=node.node_id,
                arrive_at=self.sim_time + delay,
            ))

    # ------------------------------------------------------------------
    def _deliver_blocks(self, result: SimulationResult):
        """Consegna i blocchi in scadenza e rileva fork/reorg."""
        due                = [e for e in self.network_queue if e.arrive_at <= self.sim_time]
        self.network_queue = [e for e in self.network_queue if e.arrive_at >  self.sim_time]

        for event in due:
            if event.target_id >= len(self.nodes):
                if self.malicious and event.target_id == self.malicious.node_id:
                    self.malicious.receive_block(event.block, self.sim_time)
                continue

            node    = self.nodes[event.target_id]
            outcome = node.receive_block(event.block, self.sim_time)

            if outcome.startswith("reorg"):
                depth = int(outcome.split("depth=")[1])
                result.reorg_events.append({
                    "time":   self.sim_time,
                    "node":   event.target_id,
                    "detail": outcome,
                    "depth":  depth,
                })
            elif outcome == "connected":
                result.fork_events.append({
                    "time":  self.sim_time,
                    "tips":  {n.node_id: n.tip.hash for n in self.nodes},
                    "count": len({n.tip.hash for n in self.nodes}),
                    "block": event.block.hash[:8],
                    "node":  event.target_id,
                })
    # ------------------------------------------------------------------
    def _reveal_malicious_chain(self, result: SimulationResult):
        """
        Il nodo malevolo pubblica tutti i blocchi segreti.
        La most-work chain rule forza i nodi onesti a riorganizzarsi.
        Le reorg generate vengono registrate con il tag :ATTACK nel detail.
        """
        if not self.malicious:
            return

        honest_max = max(n.chain_work for n in self.nodes)
        mal_work   = self.malicious.chain_work

        print(f"\n*** REVEAL ATTACCO t={self.sim_time:.0f}s ***")
        print(f"malevolo={mal_work} onesti={honest_max}")

        if mal_work <= honest_max:
            print("Attacco fallito: catena troppo corta")
            self.malicious_reveal_at = None
            return

        print("Attacco potenzialmente valido: propagazione blocchi")

        for block in self.malicious.blockchain.chain[1:]:
            for node in self.nodes:
                height_before = node.height
                outcome       = node.receive_block(block, self.sim_time)
                if outcome.startswith("reorg"):
                    depth = int(outcome.split("depth=")[1])
                    result.reorg_events.append({
                        "time":   self.sim_time,
                        "node":   node.node_id,
                        "detail": outcome + ":ATTACK",
                        "depth":  depth,
                    })

        self.malicious_reveal_at = None

    # ------------------------------------------------------------------
    def _snapshot(self) -> dict:
        snap = {"time": self.sim_time}
        for node in self.nodes:
            snap[f"node_{node.node_id}"] = {
                "height":     node.height,
                "chain_work": node.chain_work,
                "stale":      node.stale_count,
                "tip":        node.tip.hash[:8],
            }
        if self.malicious:
            snap["malicious"] = {
                "height":     self.malicious.height,
                "chain_work": self.malicious.chain_work,
            }
        return snap

    def _final_chains(self) -> dict:
        chains = {}
        for node in self.nodes:
            chains[node.node_id] = {
                "chain": [(b.index, b.hash[:8], b.miner_id)
                          for b in node.blockchain.chain],
                "stale": [(b.index, b.hash[:8], b.miner_id)
                          for b in node.blockchain.stale_blocks.values()],
            }
        return chains