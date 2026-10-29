"""Q-Transplant v4 — Persistent SHA-256 Cryptographic Audit Ledger.

Blocks are stored in SQLite via AuditLedgerBlock model.
Chain is loaded from DB on startup so it survives server restarts.
"""
import hashlib
import json
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("qtransplant.ledger")


class AuditBlock:
    def __init__(self, index: int, timestamp: float, action: str,
                 details: Dict[str, Any], previous_hash: str, existing_hash: str = None):
        self.index = index
        self.timestamp = timestamp
        self.action = action
        self.details = details
        self.previous_hash = previous_hash
        self.hash = existing_hash or self._calculate_hash()

    def _calculate_hash(self) -> str:
        block_str = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "details": self.details,
            "previous_hash": self.previous_hash,
        }, sort_keys=True, default=str)
        return hashlib.sha256(block_str.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "action": self.action,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
        }


class PersistentAuditLedger:
    """In-memory chain backed by SQLite persistence."""

    def __init__(self):
        self.chain: List[AuditBlock] = []
        self._db_loaded = False

    def load_from_db(self, db):
        """Load existing chain from SQLite on startup."""
        from app.models import AuditLedgerBlock
        blocks = db.query(AuditLedgerBlock).order_by(AuditLedgerBlock.block_index).all()
        if blocks:
            self.chain = [
                AuditBlock(
                    index=b.block_index,
                    timestamp=b.timestamp,
                    action=b.action,
                    details=b.details or {},
                    previous_hash=b.previous_hash,
                    existing_hash=b.block_hash,
                )
                for b in blocks
            ]
            logger.info(f"Loaded {len(self.chain)} audit blocks from DB.")
        else:
            self._create_genesis(db)
        self._db_loaded = True

    def _create_genesis(self, db=None):
        genesis = AuditBlock(
            index=0,
            timestamp=time.time(),
            action="GENESIS_BLOCK_INITIALIZATION",
            details={"system": "Q-Transplant v4 Immutable Audit Ledger",
                     "network": "National Organ Allocation Grid - India"},
            previous_hash="0" * 64,
        )
        self.chain.append(genesis)
        if db:
            self._persist_block(genesis, db)

    def _persist_block(self, block: AuditBlock, db):
        from app.models import AuditLedgerBlock
        try:
            row = AuditLedgerBlock(
                block_index=block.index,
                action=block.action,
                details=block.details,
                block_hash=block.hash,
                previous_hash=block.previous_hash,
                timestamp=block.timestamp,
            )
            db.add(row)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to persist ledger block: {e}")

    def add_block(self, action: str, details: Dict[str, Any], db=None) -> AuditBlock:
        latest = self.chain[-1] if self.chain else None
        prev_hash = latest.hash if latest else "0" * 64
        block = AuditBlock(
            index=len(self.chain),
            timestamp=time.time(),
            action=action,
            details=details,
            previous_hash=prev_hash,
        )
        self.chain.append(block)
        if db:
            self._persist_block(block, db)
        return block

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            cur = self.chain[i]
            prev = self.chain[i - 1]
            if cur.hash != cur._calculate_hash():
                return False
            if cur.previous_hash != prev.hash:
                return False
        return True

    def get_chain_dicts(self) -> List[Dict[str, Any]]:
        return [b.to_dict() for b in self.chain]

    @property
    def total_blocks(self) -> int:
        return len(self.chain)


# Global singleton — loaded with DB on app startup
audit_ledger = PersistentAuditLedger()
