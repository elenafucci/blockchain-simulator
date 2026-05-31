"""
node.py
=======
Modello di un nodo/miner della rete Bitcoin semplificata.

Ogni nodo:
  - riceve e valida blocchi propagati dalla rete
  - mantiene una vista locale della blockchain
  - espone il proprio hash power, utilizzato dal simulatore
    per determinare la probabilità di mining
"""

import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from blockchain import Block, Blockchain, make_genesis


# ---------------------------------------------------------------------------
# Evento di rete: un blocco in transito
# ---------------------------------------------------------------------------

@dataclass
class NetworkEvent:
    """
    Rappresenta un blocco in propagazione sulla rete P2P.

    In Bitcoin il protocollo di propagazione funziona così:
      1. Il miner invia un messaggio 'inv' (inventory) ai peer
      2. I peer rispondono con 'getdata' se non conoscono il blocco
      3. Il miner invia il blocco completo con 'block'
    Con compact blocks (BIP152) il processo è più veloce.
    Qui simuliamo direttamente la consegna con un ritardo.
    """
    block:     Block
    target_id: int      # id del nodo destinatario
    arrive_at: float    # tempo simulato di arrivo (secondi)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class Node:
    """
    Nodo della rete Bitcoin semplificata.

    Parametri:
      node_id    : identificatore univoco
      hash_power : potenza di mining relativa (es. 1.0 = normale,
                   2.0 = doppia potenza, 0.5 = metà potenza)
      difficulty : numero di zeri esadecimali richiesti per il PoW
      is_malicious: se True, il nodo mina in segreto (scenario 51%)
    """

    def __init__(
        self,
        node_id:      int,
        hash_power:   float,
        genesis:      Block,
        difficulty:   int   = 4,
        is_malicious: bool  = False,
    ):
        self.node_id      = node_id
        self.hash_power   = hash_power
        self.difficulty   = difficulty
        self.is_malicious = is_malicious

        # Catena locale
        self.blockchain = Blockchain(genesis)

        # Mempool: transazioni in attesa di essere incluse in un blocco.
        # In Bitcoin reale la mempool è un insieme ordinato per fee/vbyte.
        # Qui usiamo un contatore semplice per simulare il contenuto.
        self.mempool_tx_count = 0

        # Log degli eventi di questo nodo (per analisi e grafici)
        self.event_log: list[dict] = []

    # ------------------------------------------------------------------
    # Ricezione di un blocco
    # ------------------------------------------------------------------

    def receive_block(self, block: Block, sim_time: float) -> str:
        """
        Elabora un blocco ricevuto dalla rete.
        Restituisce l'esito (extended / reorg / stale / duplicate / invalid).
        """
        result = self.blockchain.add_block(block)
        self._log(result, sim_time, block=block)
        return result

    # ------------------------------------------------------------------
    # Stato
    # ------------------------------------------------------------------

    @property
    def tip(self) -> Block:
        return self.blockchain.tip

    @property
    def height(self) -> int:
        return self.blockchain.height

    @property
    def chain_work(self) -> int:
        return self.blockchain.chain_work

    @property
    def stale_count(self) -> int:
        return len(self.blockchain.stale_blocks)

    # ------------------------------------------------------------------
    # Log interno
    # ------------------------------------------------------------------

    def _log(self, event_type: str, sim_time: float, block: Optional[Block] = None):
        entry = {
            "time":       sim_time,
            "node":       self.node_id,
            "event":      event_type,
            "height":     self.height,
            "chain_work": self.chain_work,
        }
        if block:
            entry["block_hash"]   = block.hash[:10]
            entry["block_height"] = block.index
            entry["miner"]        = block.miner_id
        self.event_log.append(entry)

    def __repr__(self) -> str:
        return (
            f"Node(id={self.node_id}, "
            f"hp={self.hash_power:.1f}, "
            f"h={self.height}, "
            f"work={self.chain_work}, "
            f"stale={self.stale_count})"
        )
