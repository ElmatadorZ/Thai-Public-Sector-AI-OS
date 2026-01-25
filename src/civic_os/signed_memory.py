CIVIC-OS Signed Memory (Append-only)
- Stores decision artifacts + audit results + falsifier results
- Signs entries to make tampering detectable
- Works locally (JSONL) by default: ./runs/<run_id>/signed_log.jsonl

Design goals:
- Simple, portable, no external deps
- Deterministic canonicalization for signing (sorted keys)
- Append-only workflow (never edit old entries)

Security note:
- This is integrity-focused, not encryption.
- Keep SIGNING_SECRET in env for stronger guarantees.

Usage:
  from civic_os.signed_memory import SignedMemory, SignedEntry
  mem = SignedMemory(run_dir="runs/demo")
  mem.append(entry)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hmac_sha256_hex(secret: bytes, msg: str) -> str:
    return hmac.new(secret, msg.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class SignedEntry:
    """
    A signed append-only log entry.

    Fields:
      - run_id: unique run identifier
      - seq: incremental sequence number (append-only)
      - event: e.g. "RUN_START" | "AUDIT_REPORT" | "FALSIFIER_RESULT" | "RUN_END"
      - payload: any dict (artifacts, reports, metrics snapshots, etc.)
      - prev_hash: chain hash (tamper-evident)
      - hash: current entry hash (sha256)
      - signature: HMAC signature (optional but recommended)
    """
    run_id: str
    seq: int
    event: str
    payload: Dict[str, Any]
    timestamp_utc: str = field(default_factory=_now_utc_iso)
    prev_hash: str = ""
    hash: str = ""
    signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "event": self.event,
            "timestamp_utc": self.timestamp_utc,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
            "signature": self.signature,
            "payload": self.payload,
        }


class SignedMemory:
    """
    Append-only signed log using a hash-chain + optional HMAC signature.

    Default storage:
      runs/<run_id>/signed_log.jsonl

    Env vars:
      SIGNING_SECRET: if set, enables HMAC signatures
    """

    def __init__(self, run_dir: str, filename: str = "signed_log.jsonl"):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.run_dir / filename

        secret = os.getenv("SIGNING_SECRET", "").encode("utf-8")
        self._secret: Optional[bytes] = secret if secret else None

        self._seq = 0
        self._prev_hash = ""
        self._load_tail()

    def _load_tail(self) -> None:
        """
        Loads last seq/hash from existing log to continue appending.
        """
        if not self.path.exists():
            return
        last_line = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last_line = line
        if not last_line:
            return
        try:
            obj = json.loads(last_line)
            self._seq = int(obj.get("seq", 0)) + 1
            self._prev_hash = str(obj.get("hash", "")) or ""
        except Exception:
            # If corrupted, do not overwrite; start new chain (still append-only)
            self._seq = 0
            self._prev_hash = ""

    def _compute_hash(self, entry_dict: Dict[str, Any]) -> str:
        # Hash excludes signature to avoid circular dependency
        d = dict(entry_dict)
        d["signature"] = ""
        return _sha256_hex(_canonical_json(d))

    def _compute_signature(self, entry_hash: str) -> str:
        if not self._secret:
            return ""
        return _hmac_sha256_hex(self._secret, entry_hash)

    def append(self, entry: SignedEntry) -> SignedEntry:
        """
        Appends an entry to the JSONL log with hash chaining + signature.
        """
        entry.seq = self._seq
        entry.prev_hash = self._prev_hash

        entry_dict = entry.to_dict()
        entry.hash = self._compute_hash(entry_dict)
        entry.signature = self._compute_signature(entry.hash)

        # Write canonical line
        with self.path.open("a", encoding="utf-8") as f:
            f.write(_canonical_json(entry.to_dict()) + "\n")

        # Advance chain
        self._prev_hash = entry.hash
        self._seq += 1
        return entry

    def verify_chain(self) -> Dict[str, Any]:
        """
        Verifies:
          - hash chain integrity
          - optional signatures (if SIGNING_SECRET is set)
        Returns a report dict.
        """
        if not self.path.exists():
            return {"ok": True, "checked": 0, "notes": ["No log found."]}

        checked = 0
        prev_hash = ""
        bad = 0
        notes = []

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                checked += 1
                obj = json.loads(line)

                # Check chain
                if obj.get("prev_hash", "") != prev_hash:
                    bad += 1
                    notes.append(f"Chain mismatch at seq={obj.get('seq')}")

                # Recompute hash
                recompute = dict(obj)
                recompute["signature"] = ""
                expected_hash = _sha256_hex(_canonical_json(recompute))
                if obj.get("hash") != expected_hash:
                    bad += 1
                    notes.append(f"Hash mismatch at seq={obj.get('seq')}")

                # Verify signature if enabled
                if self._secret:
                    expected_sig = _hmac_sha256_hex(self._secret, expected_hash)
                    if obj.get("signature") != expected_sig:
                        bad += 1
                        notes.append(f"Signature mismatch at seq={obj.get('seq')}")

                prev_hash = obj.get("hash", "")

        return {
            "ok": bad == 0,
            "checked": checked,
            "bad": bad,
            "notes": notes[:20],
            "signature_enabled": bool(self._secret),
        }
