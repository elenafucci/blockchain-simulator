"""
blockchain.py
=============
Strutture dati fondamentali del simulatore:
  - Block       : rappresenta un singolo blocco
  - Blockchain  : catena locale di un nodo + logica di consenso
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclass
class Block:
    """
    Rappresenta un blocco della blockchain.

    Campi corrispondenti all'header reale di Bitcoin:
      - index        <-> block height
      - prev_hash    <-> hashPrevBlock
      - merkle_root  <-> hashMerkleRoot (hash delle tx come stringa)
      - timestamp    <-> nTime          (tempo simulato in secondi)
      - difficulty   <-> nBits          (numero di zeri esadecimali richiesti)
      - nonce        <-> nNonce
      - hash         <-> risultato del double-SHA256 sull'header

    chain_work: proof-of-work cumulativa dalla genesi fino a questo blocco.
    In Bitcoin reale:
        chain_work += 2**256 // target
    Qui semplifichiamo:
        chain_work += difficulty   (monotonicamente crescente)
    La regola di selezione e' comunque corretta:
        "vince la catena con il chain_work massimo"
    """
    index:       int
    prev_hash:   str
    merkle_root: str
    timestamp:   float
    difficulty:  int
    nonce:       int  = 0
    hash:        str  = field(default="", init=False)
    chain_work:  int  = field(default=0,  init=False)
    miner_id:    int  = -1

    def compute_hash(self) -> str:
        """
        Double-SHA256 sul contenuto dell'header, come in Bitcoin:
            SHA256(SHA256(version || prev_hash || merkle_root ||
                          timestamp || bits || nonce))
        """
        header = (
            f"{self.index}"
            f"{self.prev_hash}"
            f"{self.merkle_root}"
            f"{self.timestamp:.6f}"
            f"{self.difficulty}"
            f"{self.nonce}"
        ).encode()
        first  = hashlib.sha256(header).digest()
        second = hashlib.sha256(first).hexdigest()
        return second

    def meets_target(self) -> bool:
        """
        Verifica hash < target.
        Qui: l'hash deve iniziare con `difficulty` zeri esadecimali.
        """
        return self.hash.startswith("0" * self.difficulty)

    def __repr__(self) -> str:
        return (f"Block(h={self.index}, hash={self.hash[:10]}..., "
                f"miner={self.miner_id}, work={self.chain_work})")


# ---------------------------------------------------------------------------
# Genesis block
# ---------------------------------------------------------------------------

def make_genesis(difficulty: int = 3) -> Block:
    g = Block(
        index=0,
        prev_hash="0" * 64,
        merkle_root="genesis",
        timestamp=0.0,
        difficulty=difficulty,
        miner_id=-1
    )
    # Il genesis block riceve un hash fittizio che soddisfa il target
    # per costruzione (inizia con `difficulty` zeri esadecimali),
    # senza eseguire vera proof-of-work. Questo è accettabile perché
    # il genesis block è un parametro fisso del protocollo, non minato
    # dinamicamente durante la simulazione.
    g.hash = "0" * difficulty + "a" * (64 - difficulty)

    # chain_work è modellato in modo semplificato come somma lineare
    # della difficulty, invece del modello reale basato su target proof-of-work
    # (che userebbe 2^256 // target). La regola di consenso rimane corretta:
    # "vince la catena con il chain_work massimo".
    g.chain_work = difficulty

    return g


# ---------------------------------------------------------------------------
# Blockchain (catena locale di un nodo)
# ---------------------------------------------------------------------------

class Blockchain:
    """
    Catena locale mantenuta da un nodo.

    Struttura interna:
      - chain       : lista ordinata di Block (catena attiva)
      - all_blocks  : dizionario hash->Block di TUTTI i blocchi noti
                      (sia attivi che stale). Equivalente a mapBlockIndex
                      in Bitcoin Core.

    La regola di consenso e' la "most-work chain rule":
        La catena attiva e' quella valida con il maggiore chain_work totale.
    """

    def __init__(self, genesis: Block):
        self.chain: list[Block]           = [genesis]
        self.all_blocks: dict[str, Block] = {genesis.hash: genesis}
        # children: hash -> lista di hash dei figli diretti
        # Permette di navigare il DAG in avanti
        self.children: dict[str, list[str]] = {genesis.hash: []}

    # ------------------------------------------------------------------
    # Proprieta' di accesso
    # ------------------------------------------------------------------

    @property
    def tip(self) -> Block:
        return self.chain[-1]

    @property
    def height(self) -> int:
        return self.tip.index

    @property
    def chain_work(self) -> int:
        return self.tip.chain_work

    @property
    def known_hashes(self) -> set:
        return set(self.all_blocks.keys())

    @property
    def stale_blocks(self) -> dict:
        """Blocchi noti ma non nella catena attiva."""
        active = {b.hash for b in self.chain}
        return {h: b for h, b in self.all_blocks.items() if h not in active}

    # ------------------------------------------------------------------
    # Aggiunta di un blocco
    # ------------------------------------------------------------------

    def add_block(self, block: Block) -> str:
        """
        Tenta di aggiungere un blocco ricevuto dalla rete.

        Restituisce:
          'extended'         - blocco estende normalmente il tip
          'reorg:X->Y:depth=N' - blocco ha causato una riorganizzazione
          'connected'        - blocco aggiunto al DAG ma non e' il tip
          'duplicate'        - blocco gia' noto
          'invalid'          - PoW non valida
          'orphan'           - padre sconosciuto
        """
        # 1. Deduplicazione
        if block.hash in self.all_blocks:
            return "duplicate"

        # 2. Validazione Proof-of-Work
        if not block.meets_target():
            return "invalid"

        # 3. Cerca il padre
        parent = self.all_blocks.get(block.prev_hash)
        if parent is None:
            return "orphan"

        # 4. Calcola chain_work dal padre
        # Nota: _do_mine calcola già chain_work in modo identico, quindi per
        # blocchi minati localmente questo è ridondante. Il ricalcolo è però
        # necessario per blocchi ricevuti dalla rete (o dalla reveal dell'attacco),
        # dove chain_work potrebbe non essere stato impostato correttamente
        # rispetto al DAG locale di questo nodo.
        block.chain_work = parent.chain_work + block.difficulty

        # 5. Registra nel DAG
        self.all_blocks[block.hash] = block
        self.children.setdefault(parent.hash, []).append(block.hash)
        self.children.setdefault(block.hash, [])

        # 6. Applica la most-work chain rule
        return self._update_tip(block)

    def _update_tip(self, new_block: Block) -> str:
        if new_block.chain_work < self.chain_work:
            return "stale"        # ramo chiaramente perdente

        if new_block.chain_work == self.chain_work:
            return "connected"    # ramo concorrente → fork reale

        # new_block.chain_work > self.chain_work → diventa il nuovo tip
        new_chain_hashes = []
        cur = new_block
        active_set = {b.hash for b in self.chain}
        while cur.hash not in active_set:
            new_chain_hashes.append(cur.hash)
            cur = self.all_blocks[cur.prev_hash]

        ancestor_idx = next(i for i, b in enumerate(self.chain)
                            if b.hash == cur.hash)
        was_extension = (new_block.prev_hash == self.tip.hash)

        reorg_depth = len(self.chain) - 1 - ancestor_idx

        self.chain = self.chain[:ancestor_idx + 1]
        for h in reversed(new_chain_hashes):
            self.chain.append(self.all_blocks[h])

        if was_extension:
            return "extended"
        else:
            return f"reorg:{cur.hash[:8]}->{new_block.hash[:8]}:depth={reorg_depth}"

    # ------------------------------------------------------------------
    # Utilita'
    # ------------------------------------------------------------------

    def get_hashes(self) -> list[str]:
        return [b.hash for b in self.chain]

    def __len__(self) -> int:
        return len(self.chain)

    def __repr__(self) -> str:
        return (f"Blockchain(height={self.height}, "
                f"work={self.chain_work}, "
                f"stale={len(self.stale_blocks)})")