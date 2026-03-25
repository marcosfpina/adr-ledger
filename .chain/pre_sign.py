"""
ADR-Ledger Pre-Signing for Critical ADRs

Collects Ed25519 signatures over an ADR's content_hash BEFORE
acceptance. Solves the chicken-and-egg problem where governance
requires signatures but the chain block only exists after accept.

Flow:
  1. `adr pre-sign ADR-XXXX --signer pina` → signs content_hash
  2. Governance engine reads pending_signatures/ during validation
  3. `cmd_accept` migrates pre-signatures into the chain block
  4. Pending signatures cleaned up after acceptance

State: .chain/pending_signatures/<ADR_ID>.json
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional

from crypto import compute_file_hash, sign_message, verify_signature, Signature

CHAIN_DIR = Path(__file__).parent
PENDING_DIR = CHAIN_DIR / "pending_signatures"
ADR_ROOT = CHAIN_DIR.parent / "adr"


@dataclass
class PreSignature:
    signer_id: str
    role: str
    public_key: str
    signature: str
    timestamp: str
    content_hash: str       # SHA256 of the ADR file at time of signing

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PreSignature":
        return cls(**d)


@dataclass
class PendingSignatures:
    adr_id: str
    content_hash: str       # Current content hash of the ADR
    signatures: List[PreSignature]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "adr_id": self.adr_id,
            "content_hash": self.content_hash,
            "signatures": [s.to_dict() for s in self.signatures],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingSignatures":
        return cls(
            adr_id=d["adr_id"],
            content_hash=d["content_hash"],
            signatures=[PreSignature.from_dict(s) for s in d.get("signatures", [])],
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


class PreSignManager:
    def __init__(self):
        PENDING_DIR.mkdir(parents=True, exist_ok=True)

    def _find_adr_file(self, adr_id: str) -> Optional[Path]:
        """Find ADR file in proposed/ directory."""
        for d in ["proposed", "accepted"]:
            matches = list((ADR_ROOT / d).glob(f"{adr_id}*.md"))
            if matches:
                return matches[0]
        return None

    def _load_pending(self, adr_id: str) -> Optional[PendingSignatures]:
        """Load pending signatures for an ADR."""
        path = PENDING_DIR / f"{adr_id}.json"
        if path.exists():
            return PendingSignatures.from_dict(json.loads(path.read_text()))
        return None

    def _save_pending(self, pending: PendingSignatures):
        """Save pending signatures."""
        path = PENDING_DIR / f"{pending.adr_id}.json"
        path.write_text(json.dumps(pending.to_dict(), indent=2) + "\n")

    def sign(self, adr_id: str, signer_name: str) -> PreSignature:
        """Pre-sign an ADR's content hash."""
        adr_file = self._find_adr_file(adr_id)
        if not adr_file:
            print(f"ERROR: ADR file not found for '{adr_id}'.", file=sys.stderr)
            sys.exit(1)

        content_hash = compute_file_hash(str(adr_file))
        pending = self._load_pending(adr_id)
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        if pending is None:
            pending = PendingSignatures(
                adr_id=adr_id,
                content_hash=content_hash,
                signatures=[],
                created_at=now,
                updated_at=now,
            )

        # Check if content changed since last signature
        if pending.content_hash != content_hash and pending.signatures:
            print(
                f"WARNING: ADR content changed since previous signatures. "
                f"Invalidating {len(pending.signatures)} existing signature(s).",
                file=sys.stderr,
            )
            pending.signatures = []
            pending.content_hash = content_hash

        # Check for duplicate signer
        for existing in pending.signatures:
            if existing.signer_id == signer_name:
                print(
                    f"ERROR: '{signer_name}' has already pre-signed {adr_id}.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Sign the content hash
        sig = sign_message(content_hash, signer_name)
        pre_sig = PreSignature(
            signer_id=sig.signer_id,
            role=sig.role,
            public_key=sig.public_key,
            signature=sig.signature,
            timestamp=sig.timestamp,
            content_hash=content_hash,
        )

        pending.signatures.append(pre_sig)
        pending.updated_at = now
        self._save_pending(pending)

        return pre_sig

    def get_signatures(self, adr_id: str) -> List[dict]:
        """Get pre-signatures as dicts (compatible with governance engine)."""
        pending = self._load_pending(adr_id)
        if not pending:
            return []

        # Verify content hash still matches
        adr_file = self._find_adr_file(adr_id)
        if adr_file:
            current_hash = compute_file_hash(str(adr_file))
            if current_hash != pending.content_hash:
                print(
                    f"WARNING: ADR content changed. Pre-signatures are stale.",
                    file=sys.stderr,
                )
                return []

        # Convert to governance-compatible dict format
        return [
            {
                "signer_id": s.signer_id,
                "role": s.role,
                "public_key": s.public_key,
                "signature": s.signature,
                "timestamp": s.timestamp,
            }
            for s in pending.signatures
        ]

    def verify(self, adr_id: str) -> dict:
        """Verify all pre-signatures for an ADR."""
        pending = self._load_pending(adr_id)
        if not pending:
            return {"valid": False, "error": "No pending signatures found"}

        adr_file = self._find_adr_file(adr_id)
        if not adr_file:
            return {"valid": False, "error": "ADR file not found"}

        current_hash = compute_file_hash(str(adr_file))
        report = {
            "adr_id": adr_id,
            "content_hash_matches": current_hash == pending.content_hash,
            "total_signatures": len(pending.signatures),
            "signatures": [],
        }

        for s in pending.signatures:
            sig = Signature(
                signer_id=s.signer_id,
                public_key=s.public_key,
                signature=s.signature,
                timestamp=s.timestamp,
                role=s.role,
            )
            valid = verify_signature(pending.content_hash, sig)
            report["signatures"].append({
                "signer": s.signer_id,
                "role": s.role,
                "valid": valid,
                "timestamp": s.timestamp,
            })

        report["valid"] = (
            report["content_hash_matches"]
            and all(s["valid"] for s in report["signatures"])
        )
        return report

    def migrate_to_block(self, adr_id: str) -> List[dict]:
        """Migrate pre-signatures to chain block format and clean up.
        Called by cmd_accept after block is created."""
        pending = self._load_pending(adr_id)
        if not pending:
            return []

        # Convert to chain block signature format
        block_sigs = []
        for s in pending.signatures:
            block_sigs.append({
                "signer_id": s.signer_id,
                "role": s.role,
                "public_key": s.public_key,
                "signature": s.signature,
                "timestamp": s.timestamp,
            })

        # Clean up pending file
        path = PENDING_DIR / f"{adr_id}.json"
        if path.exists():
            path.unlink()

        return block_sigs

    def clean(self, adr_id: str):
        """Remove pending signatures for an ADR."""
        path = PENDING_DIR / f"{adr_id}.json"
        if path.exists():
            path.unlink()
            print(f"Cleaned pending signatures for {adr_id}")
        else:
            print(f"No pending signatures found for {adr_id}")

    def list_pending(self) -> List[dict]:
        """List all ADRs with pending signatures."""
        results = []
        for f in sorted(PENDING_DIR.glob("ADR-*.json")):
            pending = PendingSignatures.from_dict(json.loads(f.read_text()))
            results.append({
                "adr_id": pending.adr_id,
                "signatures": len(pending.signatures),
                "signers": [s.signer_id for s in pending.signatures],
                "updated_at": pending.updated_at,
            })
        return results

    def status(self, adr_id: str):
        """Print status of pre-signatures for an ADR."""
        pending = self._load_pending(adr_id)
        if not pending:
            print(f"No pending signatures for {adr_id}")
            return

        adr_file = self._find_adr_file(adr_id)
        content_match = "MATCH" if adr_file and compute_file_hash(str(adr_file)) == pending.content_hash else "STALE"

        print(f"Pre-signatures for {adr_id}:")
        print(f"  Content hash: {pending.content_hash[:16]}... [{content_match}]")
        print(f"  Signatures:   {len(pending.signatures)}")
        for s in pending.signatures:
            print(f"    - {s.signer_id} ({s.role}) at {s.timestamp}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ADR-Ledger Pre-Signing")
    sub = parser.add_subparsers(dest="command")

    # sign
    sign_p = sub.add_parser("sign", help="Pre-sign an ADR's content hash")
    sign_p.add_argument("adr_id", help="ADR ID (e.g., ADR-0032)")
    sign_p.add_argument("--signer", required=True, help="Signer name")

    # verify
    verify_p = sub.add_parser("verify", help="Verify pre-signatures")
    verify_p.add_argument("adr_id", help="ADR ID")

    # status
    status_p = sub.add_parser("status", help="Show pre-signature status")
    status_p.add_argument("adr_id", help="ADR ID")

    # list
    sub.add_parser("list", help="List all pending pre-signatures")

    # clean
    clean_p = sub.add_parser("clean", help="Remove pending signatures")
    clean_p.add_argument("adr_id", help="ADR ID")

    args = parser.parse_args()
    manager = PreSignManager()

    if args.command == "sign":
        pre_sig = manager.sign(args.adr_id, args.signer)
        print(f"Pre-signed {args.adr_id} by {pre_sig.signer_id} ({pre_sig.role})")
        print(f"  Content hash: {pre_sig.content_hash[:16]}...")
        print(f"  Signature:    {pre_sig.signature[:32]}...")

    elif args.command == "verify":
        report = manager.verify(args.adr_id)
        status = "VALID" if report["valid"] else "INVALID"
        print(f"Pre-signature verification for {args.adr_id}: {status}")
        print(f"  Content hash match: {report['content_hash_matches']}")
        for s in report.get("signatures", []):
            symbol = "OK" if s["valid"] else "FAIL"
            print(f"  [{symbol}] {s['signer']} ({s['role']})")
        sys.exit(0 if report["valid"] else 1)

    elif args.command == "status":
        manager.status(args.adr_id)

    elif args.command == "list":
        pending = manager.list_pending()
        if not pending:
            print("No pending pre-signatures")
        else:
            for p in pending:
                signers = ", ".join(p["signers"])
                print(f"  {p['adr_id']}: {p['signatures']} sig(s) [{signers}]")

    elif args.command == "clean":
        manager.clean(args.adr_id)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
