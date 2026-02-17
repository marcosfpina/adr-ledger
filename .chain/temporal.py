"""
ADR-Ledger Temporal Anchoring — OpenTimestamps Integration

Proves externally (via Bitcoin blockchain) that decisions existed at a
specific point in time, independent of Git history.

Workflow:
  1. ots stamp <hash_file>       → creates .ots proof (pending Bitcoin)
  2. ots upgrade <file>.ots      → upgrades with Bitcoin merkle path (~2-12h)
  3. ots verify <file>.ots       → verifies against Bitcoin blockchain
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

CHAIN_DIR = Path(__file__).parent
TIMESTAMPS_DIR = CHAIN_DIR / "timestamps"
STATE_FILE = TIMESTAMPS_DIR / "temporal_state.json"
SNAPSHOTS_DIR = CHAIN_DIR / "snapshots"
MERKLE_STATE_FILE = CHAIN_DIR / "merkle" / "merkle_state.json"
GOVERNANCE_FILE = CHAIN_DIR.parent / ".governance" / "governance.yaml"


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class TimestampProof:
    proof_id: str               # "ts_NNNN" (sequential)
    target_type: str            # "snapshot" | "merkle_root" | "block" | "sbom"
    target_id: str              # snapshot_id, block_hash, etc.
    target_hash: str            # SHA256 being anchored
    ots_file: str               # relative path to .ots file
    status: str                 # "pending" | "upgraded" | "verified" | "failed"
    created_at: str             # ISO 8601
    upgraded_at: Optional[str] = None   # when Bitcoin confirmed
    verified_at: Optional[str] = None   # last verification
    bitcoin_block: Optional[int] = None # Bitcoin block height (after upgrade)
    calendar_urls: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TimestampProof":
        return cls(**d)


@dataclass
class TemporalState:
    version: str = "1.0"
    total_proofs: int = 0
    pending_count: int = 0
    verified_count: int = 0
    proofs: List[TimestampProof] = field(default_factory=list)
    last_anchor: Optional[str] = None  # ISO 8601

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TemporalState":
        proofs = [TimestampProof.from_dict(p) for p in d.get("proofs", [])]
        return cls(
            version=d.get("version", "1.0"),
            total_proofs=d.get("total_proofs", 0),
            pending_count=d.get("pending_count", 0),
            verified_count=d.get("verified_count", 0),
            proofs=proofs,
            last_anchor=d.get("last_anchor"),
        )


# =============================================================================
# TEMPORAL MANAGER
# =============================================================================

class TemporalManager:
    """Manages OpenTimestamps proofs for ADR-Ledger."""

    def __init__(self, timestamps_dir: Optional[Path] = None):
        self.timestamps_dir = timestamps_dir or TIMESTAMPS_DIR
        self.timestamps_dir.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()

    # ── state persistence ─────────────────────────────────────────────

    def _load_state(self) -> TemporalState:
        if STATE_FILE.exists():
            try:
                return TemporalState.from_dict(json.loads(STATE_FILE.read_text()))
            except (json.JSONDecodeError, KeyError):
                pass
        return TemporalState()

    def _save_state(self) -> None:
        self._recount()
        STATE_FILE.write_text(json.dumps(self.state.to_dict(), indent=2) + "\n")

    def _recount(self) -> None:
        self.state.total_proofs = len(self.state.proofs)
        self.state.pending_count = sum(
            1 for p in self.state.proofs if p.status == "pending"
        )
        self.state.verified_count = sum(
            1 for p in self.state.proofs if p.status == "verified"
        )

    # ── governance check ──────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Check if temporal anchoring is enabled in governance.yaml."""
        if not GOVERNANCE_FILE.exists():
            return False
        try:
            import yaml
            gov = yaml.safe_load(GOVERNANCE_FILE.read_text())
            chain_cfg = gov.get("chain", {})
            ts_cfg = chain_cfg.get("timestamp_anchoring", {})
            return ts_cfg.get("enabled", False)
        except Exception:
            return False

    # ── ots CLI interaction ───────────────────────────────────────────

    def _check_ots_available(self) -> bool:
        """Check if ots CLI is on PATH."""
        try:
            r = subprocess.run(
                ["ots", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _run_ots(self, args: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
        """Execute ots command, exit if not available."""
        try:
            return subprocess.run(
                ["ots"] + args,
                capture_output=True, text=True, timeout=timeout,
            )
        except FileNotFoundError:
            print("ERROR: 'ots' not found. Install: nix shell nixpkgs#opentimestamps-client")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            print(f"ERROR: ots command timed out after {timeout}s")
            sys.exit(1)

    # ── next proof id ─────────────────────────────────────────────────

    def _next_proof_id(self) -> str:
        if not self.state.proofs:
            return "ts_0001"
        last_num = max(
            int(p.proof_id.split("_")[1]) for p in self.state.proofs
        )
        return f"ts_{last_num + 1:04d}"

    # ── core stamping ─────────────────────────────────────────────────

    def stamp(self, target_hash: str, target_type: str, target_id: str,
              metadata: Optional[Dict[str, Any]] = None) -> TimestampProof:
        """Stamp a hash via OpenTimestamps."""
        proof_id = self._next_proof_id()

        # Write hash to temp file
        hash_file = self.timestamps_dir / f"hash_{proof_id}.txt"
        hash_file.write_text(target_hash + "\n")

        # Run ots stamp
        result = self._run_ots(["stamp", str(hash_file)])

        ots_file = self.timestamps_dir / f"hash_{proof_id}.txt.ots"

        if result.returncode != 0 or not ots_file.exists():
            print(f"WARNING: ots stamp returned code {result.returncode}")
            if result.stderr:
                print(f"  stderr: {result.stderr.strip()}")
            # Create proof with failed status if .ots wasn't generated
            if not ots_file.exists():
                proof = TimestampProof(
                    proof_id=proof_id,
                    target_type=target_type,
                    target_id=target_id,
                    target_hash=target_hash,
                    ots_file="",
                    status="failed",
                    created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    metadata=metadata or {},
                )
                self.state.proofs.append(proof)
                self._save_state()
                return proof

        # Extract calendar URLs from stderr (ots prints submission info there)
        calendar_urls = []
        for line in (result.stderr or "").splitlines():
            if "calendar" in line.lower() or "://" in line:
                url = line.strip()
                if url:
                    calendar_urls.append(url)

        ts_now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        proof = TimestampProof(
            proof_id=proof_id,
            target_type=target_type,
            target_id=target_id,
            target_hash=target_hash,
            ots_file=str(ots_file.relative_to(CHAIN_DIR)),
            status="pending",
            created_at=ts_now,
            calendar_urls=calendar_urls,
            metadata=metadata or {},
        )

        self.state.proofs.append(proof)
        self.state.last_anchor = ts_now
        self._save_state()

        return proof

    # ── convenience stampers ──────────────────────────────────────────

    def stamp_snapshot(self, snapshot_id: Optional[int] = None) -> TimestampProof:
        """Stamp the hash of a snapshot (default: latest)."""
        if snapshot_id is not None:
            snap_file = SNAPSHOTS_DIR / f"snapshot_{snapshot_id:04d}.json"
        else:
            files = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"))
            if not files:
                print("ERROR: No snapshots found. Run: adr snapshot create")
                sys.exit(1)
            snap_file = files[-1]

        snap = json.loads(snap_file.read_text())
        snap_hash = snap["snapshot_hash"]
        snap_id = snap["snapshot_id"]

        return self.stamp(
            target_hash=snap_hash,
            target_type="snapshot",
            target_id=f"snapshot_{snap_id:04d}",
            metadata={"chain_height": snap.get("chain_height"),
                       "merkle_root": snap.get("merkle_root", "")[:32]},
        )

    def stamp_merkle_root(self) -> TimestampProof:
        """Stamp the current Merkle root."""
        if not MERKLE_STATE_FILE.exists():
            print("ERROR: No Merkle state found. Run: adr chain merkle-rebuild")
            sys.exit(1)

        merkle = json.loads(MERKLE_STATE_FILE.read_text())
        root_hash = merkle["root_hash"]

        return self.stamp(
            target_hash=root_hash,
            target_type="merkle_root",
            target_id="merkle_current",
            metadata={"leaf_count": merkle.get("leaf_count", 0),
                       "tree_depth": merkle.get("tree_depth", 0)},
        )

    # ── upgrade & verify ──────────────────────────────────────────────

    def upgrade_all(self) -> List[dict]:
        """Try to upgrade all pending proofs with Bitcoin merkle path."""
        results = []
        for proof in self.state.proofs:
            if proof.status != "pending":
                continue

            ots_path = CHAIN_DIR / proof.ots_file
            if not ots_path.exists():
                results.append({"proof_id": proof.proof_id, "result": "ots_file_missing"})
                continue

            result = self._run_ots(["upgrade", str(ots_path)])

            if "already" in (result.stdout + result.stderr).lower():
                # Already upgraded / has Bitcoin attestation
                proof.status = "upgraded"
                proof.upgraded_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                results.append({"proof_id": proof.proof_id, "result": "already_upgraded"})
            elif result.returncode == 0 and "success" in (result.stdout + result.stderr).lower():
                proof.status = "upgraded"
                proof.upgraded_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                results.append({"proof_id": proof.proof_id, "result": "upgraded"})
            else:
                # Still pending (Bitcoin confirmation takes ~2-12h)
                results.append({"proof_id": proof.proof_id, "result": "still_pending",
                                "detail": (result.stderr or result.stdout).strip()[:200]})

        self._save_state()
        return results

    def verify(self, proof_id: Optional[str] = None) -> List[dict]:
        """Verify proof(s). If proof_id is None, verify all."""
        targets = self.state.proofs if proof_id is None else [
            p for p in self.state.proofs if p.proof_id == proof_id
        ]

        if proof_id and not targets:
            print(f"ERROR: Proof '{proof_id}' not found")
            sys.exit(1)

        results = []
        for proof in targets:
            if not proof.ots_file:
                results.append({"proof_id": proof.proof_id, "valid": False, "detail": "no_ots_file"})
                continue

            ots_path = CHAIN_DIR / proof.ots_file
            hash_path = ots_path.with_suffix("")  # remove .ots

            if not ots_path.exists():
                results.append({"proof_id": proof.proof_id, "valid": False, "detail": "ots_file_missing"})
                continue
            if not hash_path.exists():
                results.append({"proof_id": proof.proof_id, "valid": False, "detail": "hash_file_missing"})
                continue

            result = self._run_ots(["verify", str(ots_path)])
            output = result.stdout + result.stderr

            if "success" in output.lower() or "attestation" in output.lower():
                proof.status = "verified"
                proof.verified_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                # Try to extract Bitcoin block height
                for line in output.splitlines():
                    if "block" in line.lower():
                        import re
                        m = re.search(r"block\s+(\d+)", line, re.IGNORECASE)
                        if m:
                            proof.bitcoin_block = int(m.group(1))
                results.append({"proof_id": proof.proof_id, "valid": True, "detail": output.strip()[:300]})
            elif "pending" in output.lower() or "calendar" in output.lower():
                results.append({"proof_id": proof.proof_id, "valid": None,
                                "detail": "pending_bitcoin_confirmation"})
            else:
                proof.status = "failed"
                results.append({"proof_id": proof.proof_id, "valid": False, "detail": output.strip()[:300]})

        self._save_state()
        return results

    def verify_by_file(self, ots_relative_path: str) -> dict:
        """Verify a proof by its .ots file path (used by snapshot_manager)."""
        for proof in self.state.proofs:
            if proof.ots_file == ots_relative_path:
                results = self.verify(proof.proof_id)
                if results:
                    return results[0]
        return {"valid": None, "status": "proof_not_found"}

    # ── reporting ─────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return summary status."""
        self._recount()
        upgraded = sum(1 for p in self.state.proofs if p.status == "upgraded")
        failed = sum(1 for p in self.state.proofs if p.status == "failed")
        return {
            "total_proofs": self.state.total_proofs,
            "pending": self.state.pending_count,
            "upgraded": upgraded,
            "verified": self.state.verified_count,
            "failed": failed,
            "last_anchor": self.state.last_anchor,
            "ots_available": self._check_ots_available(),
            "anchoring_enabled": self.is_enabled(),
        }

    def list_proofs(self, filter_status: Optional[str] = None) -> List[dict]:
        """List proofs with optional status filter."""
        proofs = self.state.proofs
        if filter_status:
            proofs = [p for p in proofs if p.status == filter_status]
        return [p.to_dict() for p in proofs]

    def get_proof(self, proof_id: str) -> Optional[TimestampProof]:
        """Get a single proof by ID."""
        for p in self.state.proofs:
            if p.proof_id == proof_id:
                return p
        return None


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ADR-Ledger Temporal Anchoring (OpenTimestamps)",
    )
    sub = parser.add_subparsers(dest="command")

    # stamp-snapshot
    ss = sub.add_parser("stamp-snapshot", help="Anchor snapshot hash (default: latest)")
    ss.add_argument("--id", type=int, default=None, help="Snapshot ID (default: latest)")

    # stamp-merkle
    sub.add_parser("stamp-merkle", help="Anchor current Merkle root")

    # stamp-hash
    sh = sub.add_parser("stamp-hash", help="Anchor an arbitrary hash")
    sh.add_argument("hash", help="SHA256 hex hash to anchor")
    sh.add_argument("--type", default="custom", help="Target type (default: custom)")
    sh.add_argument("--id", default="manual", help="Target ID (default: manual)")

    # upgrade
    sub.add_parser("upgrade", help="Try to upgrade all pending proofs")

    # verify
    vf = sub.add_parser("verify", help="Verify proof(s)")
    vf.add_argument("--id", default=None, help="Proof ID (default: all)")

    # status
    sub.add_parser("status", help="Summary of temporal state")

    # list
    ls = sub.add_parser("list", help="List all proofs")
    ls.add_argument("--status", default=None, help="Filter by status")

    # show
    sw = sub.add_parser("show", help="Show proof details")
    sw.add_argument("proof_id", help="Proof ID (e.g. ts_0001)")

    args = parser.parse_args()
    tm = TemporalManager()

    if args.command == "stamp-snapshot":
        proof = tm.stamp_snapshot(snapshot_id=args.id)
        print(f"Stamped snapshot → {proof.proof_id}")
        print(f"  Hash:   {proof.target_hash[:32]}...")
        print(f"  Status: {proof.status}")
        print(f"  OTS:    {proof.ots_file}")
        if proof.status == "pending":
            print("  Note:   Bitcoin confirmation takes ~2-12h. Run 'adr anchor upgrade' later.")

    elif args.command == "stamp-merkle":
        proof = tm.stamp_merkle_root()
        print(f"Stamped Merkle root → {proof.proof_id}")
        print(f"  Hash:   {proof.target_hash[:32]}...")
        print(f"  Status: {proof.status}")
        print(f"  OTS:    {proof.ots_file}")

    elif args.command == "stamp-hash":
        proof = tm.stamp(target_hash=args.hash, target_type=args.type, target_id=args.id)
        print(f"Stamped hash → {proof.proof_id}")
        print(f"  Hash:   {proof.target_hash[:32]}...")
        print(f"  Status: {proof.status}")

    elif args.command == "upgrade":
        results = tm.upgrade_all()
        if not results:
            print("No pending proofs to upgrade.")
        else:
            for r in results:
                print(f"  {r['proof_id']}: {r['result']}")
                if "detail" in r:
                    print(f"    {r['detail'][:120]}")

    elif args.command == "verify":
        results = tm.verify(proof_id=args.id)
        if not results:
            print("No proofs to verify.")
        else:
            for r in results:
                status_str = "VALID" if r["valid"] is True else ("PENDING" if r["valid"] is None else "INVALID")
                print(f"  {r['proof_id']}: {status_str}")
                if "detail" in r:
                    print(f"    {r['detail'][:120]}")

    elif args.command == "status":
        s = tm.status()
        print("Temporal Anchoring Status:")
        print(f"  Enabled:   {s['anchoring_enabled']}")
        print(f"  OTS CLI:   {'available' if s['ots_available'] else 'NOT FOUND'}")
        print(f"  Total:     {s['total_proofs']} proofs")
        print(f"  Pending:   {s['pending']}")
        print(f"  Upgraded:  {s['upgraded']}")
        print(f"  Verified:  {s['verified']}")
        print(f"  Failed:    {s['failed']}")
        if s["last_anchor"]:
            print(f"  Last:      {s['last_anchor']}")

    elif args.command == "list":
        proofs = tm.list_proofs(filter_status=args.status)
        if not proofs:
            print("No proofs found.")
            return
        print(f"{'ID':>10}  {'Type':12s}  {'Status':10s}  {'Created':25s}  {'Hash'}")
        print("-" * 90)
        for p in proofs:
            print(f"{p['proof_id']:>10}  {p['target_type']:12s}  {p['status']:10s}  "
                  f"{p['created_at']:25s}  {p['target_hash'][:16]}...")

    elif args.command == "show":
        proof = tm.get_proof(args.proof_id)
        if not proof:
            print(f"Proof '{args.proof_id}' not found", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(proof.to_dict(), indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
