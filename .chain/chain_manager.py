"""
ADR-Ledger Decision Chain (Private Blockchain)

Each accepted ADR becomes a block in a hash-linked chain.
The chain provides tamper-evident ordering and cryptographic
integrity for architectural decisions.

Chain state is persisted in .chain/chain.json (append-only).
"""

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from glob import glob
from pathlib import Path
from typing import Dict, List, Optional

from crypto import (
    Signature,
    compute_block_hash,
    compute_file_hash,
    sign_message,
    verify_signature,
)

CHAIN_DIR = Path(__file__).parent
CHAIN_FILE = CHAIN_DIR / "chain.json"
ADR_ROOT = CHAIN_DIR.parent / "adr"
GENESIS_HASH = "0" * 64


@dataclass
class ChainBlock:
    block_number: int
    adr_id: str
    content_hash: str       # SHA256 of entire ADR .md file
    previous_hash: str      # Hash of previous block (GENESIS_HASH for block 0)
    timestamp: str          # ISO 8601
    signatures: List[dict]  # List of Signature dicts
    block_hash: str         # SHA256(block_number|adr_id|content_hash|previous_hash|timestamp)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChainBlock":
        return cls(**d)

    def recompute_hash(self) -> str:
        return compute_block_hash(
            self.block_number,
            self.adr_id,
            self.content_hash,
            self.previous_hash,
            self.timestamp,
        )


@dataclass
class ChainState:
    version: str
    chain: List[ChainBlock]
    tip: str                 # block_hash of latest block
    height: int              # Number of blocks

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "chain": [b.to_dict() for b in self.chain],
            "tip": self.tip,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ChainState":
        blocks = [ChainBlock.from_dict(b) for b in d.get("chain", [])]
        return cls(
            version=d.get("version", "1.0"),
            chain=blocks,
            tip=d.get("tip", GENESIS_HASH),
            height=d.get("height", 0),
        )


class ChainManager:
    """Manages the ADR decision chain (private blockchain)."""

    def __init__(self, chain_file: Optional[Path] = None, adr_root: Optional[Path] = None):
        self.chain_file = chain_file or CHAIN_FILE
        self.adr_root = adr_root or ADR_ROOT
        self.state: Optional[ChainState] = None

    def load(self) -> ChainState:
        """Load chain state from disk."""
        if not self.chain_file.exists():
            self.state = ChainState(version="1.0", chain=[], tip=GENESIS_HASH, height=0)
            return self.state

        data = json.loads(self.chain_file.read_text())
        self.state = ChainState.from_dict(data)
        return self.state

    def save(self):
        """Save chain state to disk."""
        if self.state is None:
            raise RuntimeError("No chain state loaded")

        self.chain_file.parent.mkdir(parents=True, exist_ok=True)
        self.chain_file.write_text(json.dumps(self.state.to_dict(), indent=2) + "\n")

    def get_tip(self) -> str:
        """Return the hash of the latest block."""
        if self.state is None:
            self.load()
        return self.state.tip

    def get_block(self, block_number: int) -> Optional[ChainBlock]:
        """Get block by number."""
        if self.state is None:
            self.load()
        if 0 <= block_number < len(self.state.chain):
            return self.state.chain[block_number]
        return None

    def get_block_by_adr(self, adr_id: str) -> Optional[ChainBlock]:
        """Find block by ADR ID."""
        if self.state is None:
            self.load()
        for block in self.state.chain:
            if block.adr_id == adr_id:
                return block
        return None

    def _find_adr_file(self, adr_id: str) -> Optional[str]:
        """Find the ADR file across all status directories."""
        for status_dir in ["accepted", "proposed", "superseded", "rejected", "deprecated"]:
            pattern = str(self.adr_root / status_dir / f"{adr_id}*.md")
            matches = glob(pattern)
            if matches:
                return matches[0]
        return None

    def append_block(self, adr_id: str, timestamp: Optional[str] = None) -> ChainBlock:
        """Append a new block to the chain for an accepted ADR."""
        if self.state is None:
            self.load()

        # Check for duplicate
        if self.get_block_by_adr(adr_id) is not None:
            print(f"ERROR: ADR '{adr_id}' already exists in chain.", file=sys.stderr)
            sys.exit(1)

        # Find and hash the ADR file
        adr_file = self._find_adr_file(adr_id)
        if adr_file is None:
            print(f"ERROR: ADR file not found for '{adr_id}'.", file=sys.stderr)
            sys.exit(1)

        content_hash = compute_file_hash(adr_file)
        previous_hash = self.state.tip if self.state.chain else GENESIS_HASH
        block_number = self.state.height
        ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%S%z")

        block_hash = compute_block_hash(
            block_number, adr_id, content_hash, previous_hash, ts
        )

        block = ChainBlock(
            block_number=block_number,
            adr_id=adr_id,
            content_hash=content_hash,
            previous_hash=previous_hash,
            timestamp=ts,
            signatures=[],
            block_hash=block_hash,
        )

        self.state.chain.append(block)
        self.state.tip = block_hash
        self.state.height = len(self.state.chain)
        self.save()

        return block

    def sign_block(self, adr_id: str, signer_name: str) -> Signature:
        """Add a signature to a block."""
        block = self.get_block_by_adr(adr_id)
        if block is None:
            print(f"ERROR: No chain block found for '{adr_id}'.", file=sys.stderr)
            sys.exit(1)

        # Check for duplicate signature
        for existing in block.signatures:
            if existing.get("signer_id") == signer_name:
                print(f"ERROR: '{signer_name}' has already signed block for {adr_id}.", file=sys.stderr)
                sys.exit(1)

        sig = sign_message(block.block_hash, signer_name)
        block.signatures.append(sig.to_dict())
        self.save()

        return sig

    def verify_chain(self) -> dict:
        """Verify the entire chain integrity. Returns verification report."""
        if self.state is None:
            self.load()

        report = {
            "height": self.state.height,
            "tip": self.state.tip,
            "blocks": [],
            "chain_valid": True,
            "errors": [],
        }

        for i, block in enumerate(self.state.chain):
            block_report = {
                "block_number": block.block_number,
                "adr_id": block.adr_id,
                "hash_valid": False,
                "link_valid": False,
                "content_valid": False,
                "signatures_valid": False,
                "signature_count": len(block.signatures),
            }

            # 1. Verify block hash
            recomputed = block.recompute_hash()
            block_report["hash_valid"] = recomputed == block.block_hash
            if not block_report["hash_valid"]:
                report["chain_valid"] = False
                report["errors"].append(
                    f"Block {i} ({block.adr_id}): block_hash mismatch "
                    f"(expected {recomputed[:16]}..., got {block.block_hash[:16]}...)"
                )

            # 2. Verify chain link
            if i == 0:
                expected_prev = GENESIS_HASH
            else:
                expected_prev = self.state.chain[i - 1].block_hash

            block_report["link_valid"] = block.previous_hash == expected_prev
            if not block_report["link_valid"]:
                report["chain_valid"] = False
                report["errors"].append(
                    f"Block {i} ({block.adr_id}): chain link broken "
                    f"(expected prev={expected_prev[:16]}..., got {block.previous_hash[:16]}...)"
                )

            # 3. Verify content hash against actual file
            if block.adr_id == "GENESIS":
                # Genesis block has no file -- its content_hash is a composite
                block_report["content_valid"] = True
            else:
                adr_file = self._find_adr_file(block.adr_id)
                if adr_file:
                    actual_hash = compute_file_hash(adr_file)
                    block_report["content_valid"] = actual_hash == block.content_hash
                    if not block_report["content_valid"]:
                        report["chain_valid"] = False
                        report["errors"].append(
                            f"Block {i} ({block.adr_id}): content tampered "
                            f"(file hash {actual_hash[:16]}... != chain hash {block.content_hash[:16]}...)"
                        )
                else:
                    report["chain_valid"] = False
                    report["errors"].append(f"Block {i} ({block.adr_id}): ADR file not found")

            # 4. Verify signatures
            sigs_valid = True
            for sig_dict in block.signatures:
                sig = Signature.from_dict(sig_dict)
                if not verify_signature(block.block_hash, sig):
                    sigs_valid = False
                    report["errors"].append(
                        f"Block {i} ({block.adr_id}): invalid signature from {sig.signer_id}"
                    )
            block_report["signatures_valid"] = sigs_valid
            if not sigs_valid:
                report["chain_valid"] = False

            report["blocks"].append(block_report)

        # 5. Verify tip and height
        if self.state.chain:
            if self.state.tip != self.state.chain[-1].block_hash:
                report["chain_valid"] = False
                report["errors"].append("Chain tip does not match last block hash")
        if self.state.height != len(self.state.chain):
            report["chain_valid"] = False
            report["errors"].append(
                f"Height mismatch: recorded {self.state.height}, actual {len(self.state.chain)}"
            )

        return report

    def init_from_existing(self, signer_name: Optional[str] = None) -> int:
        """Initialize chain from existing accepted ADRs (migration).

        Creates a genesis block and individual blocks for each existing ADR,
        ordered by date from frontmatter.

        Returns the number of blocks created.
        """
        if self.state is None:
            self.load()

        if self.state.chain:
            print("ERROR: Chain already initialized. Cannot re-init.", file=sys.stderr)
            sys.exit(1)

        import re
        import yaml

        accepted_dir = self.adr_root / "accepted"
        if not accepted_dir.exists():
            print("No accepted ADRs found.", file=sys.stderr)
            return 0

        # Collect ADRs with their dates
        adr_entries = []
        frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

        for md_file in sorted(accepted_dir.glob("ADR-*.md")):
            content = md_file.read_text()
            match = frontmatter_re.match(content)
            if match:
                try:
                    fm = yaml.safe_load(match.group(1))
                    adr_id = fm.get("id", md_file.stem.split("-")[0] + "-" + md_file.stem.split("-")[1]
                                    if "-" in md_file.stem else md_file.stem)
                    # Extract just ADR-XXXX from id
                    if isinstance(adr_id, str) and adr_id.startswith("ADR-"):
                        adr_id = adr_id[:8]  # ADR-XXXX
                    date = str(fm.get("date", "1970-01-01"))
                    adr_entries.append((date, adr_id, str(md_file)))
                except yaml.YAMLError:
                    adr_entries.append(("1970-01-01", md_file.stem, str(md_file)))

        # Sort by date
        adr_entries.sort(key=lambda x: x[0])

        if not adr_entries:
            print("No accepted ADRs found to initialize chain.", file=sys.stderr)
            return 0

        # Create genesis block (captures the collective state)
        genesis_content = "|".join(
            compute_file_hash(path) for _, _, path in adr_entries
        )
        genesis_hash = compute_file_hash.__wrapped__(genesis_content) if hasattr(compute_file_hash, '__wrapped__') else \
            __import__("hashlib").sha256(genesis_content.encode("utf-8")).hexdigest()

        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        genesis_block_hash = compute_block_hash(0, "GENESIS", genesis_hash, GENESIS_HASH, ts)
        genesis = ChainBlock(
            block_number=0,
            adr_id="GENESIS",
            content_hash=genesis_hash,
            previous_hash=GENESIS_HASH,
            timestamp=ts,
            signatures=[],
            block_hash=genesis_block_hash,
        )

        self.state.chain.append(genesis)
        self.state.tip = genesis_block_hash
        self.state.height = 1

        # Create individual blocks for each ADR
        for date, adr_id, file_path in adr_entries:
            content_hash = compute_file_hash(file_path)
            previous_hash = self.state.tip
            block_number = self.state.height
            block_ts = f"{date}T00:00:00+0000"

            block_hash = compute_block_hash(
                block_number, adr_id, content_hash, previous_hash, block_ts
            )

            block = ChainBlock(
                block_number=block_number,
                adr_id=adr_id,
                content_hash=content_hash,
                previous_hash=previous_hash,
                timestamp=block_ts,
                signatures=[],
                block_hash=block_hash,
            )

            self.state.chain.append(block)
            self.state.tip = block_hash
            self.state.height += 1

        # Sign all blocks if signer provided
        if signer_name:
            for block in self.state.chain:
                sig = sign_message(block.block_hash, signer_name)
                block.signatures.append(sig.to_dict())

        self.save()
        return self.state.height

    def status(self) -> dict:
        """Return chain status summary."""
        if self.state is None:
            self.load()

        if not self.state.chain:
            return {"initialized": False, "height": 0}

        last = self.state.chain[-1]
        signed_count = sum(1 for b in self.state.chain if b.signatures)
        unsigned_count = self.state.height - signed_count

        return {
            "initialized": True,
            "version": self.state.version,
            "height": self.state.height,
            "tip": self.state.tip[:16] + "...",
            "last_block": {
                "adr_id": last.adr_id,
                "timestamp": last.timestamp,
                "signatures": len(last.signatures),
            },
            "signed_blocks": signed_count,
            "unsigned_blocks": unsigned_count,
        }


# --- CLI ---

def print_report(report: dict):
    """Pretty-print chain verification report."""
    print("=" * 60)
    print("  ADR-Ledger Chain Verification Report")
    print("=" * 60)
    print(f"  Height: {report['height']} blocks")
    print(f"  Tip:    {report['tip'][:32]}...")
    print()

    for br in report["blocks"]:
        status_parts = []
        if br["hash_valid"]:
            status_parts.append("hash:OK")
        else:
            status_parts.append("hash:FAIL")
        if br["link_valid"]:
            status_parts.append("link:OK")
        else:
            status_parts.append("link:FAIL")
        if br["content_valid"]:
            status_parts.append("content:OK")
        else:
            status_parts.append("content:FAIL")

        sigs = f"sigs:{br['signature_count']}"
        status = " ".join(status_parts)
        symbol = "PASS" if all([br["hash_valid"], br["link_valid"], br["content_valid"]]) else "FAIL"

        print(f"  Block {br['block_number']:3d} ({br['adr_id']:12s}): {symbol} [{status}] [{sigs}]")

    print()
    if report["chain_valid"]:
        print("  Chain integrity: VALID")
    else:
        print("  Chain integrity: INVALID")
        for err in report["errors"]:
            print(f"    ERROR: {err}")
    print("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="ADR-Ledger Chain Manager")
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help="Initialize chain from existing accepted ADRs")
    init_p.add_argument("--signer", help="Sign all blocks with this key")

    # append
    app_p = sub.add_parser("append", help="Append a new block for an accepted ADR")
    app_p.add_argument("adr_id", help="ADR ID (e.g., ADR-0032)")

    # sign
    sign_p = sub.add_parser("sign", help="Sign a block")
    sign_p.add_argument("adr_id", help="ADR ID")
    sign_p.add_argument("--signer", required=True, help="Signer name")

    # verify
    sub.add_parser("verify", help="Verify entire chain integrity")

    # status
    sub.add_parser("status", help="Show chain status")

    # show
    show_p = sub.add_parser("show", help="Show a specific block")
    show_p.add_argument("adr_id", help="ADR ID or block number")

    args = parser.parse_args()
    cm = ChainManager()

    if args.command == "init":
        count = cm.init_from_existing(signer_name=args.signer)
        print(f"Chain initialized with {count} blocks (including genesis).")
        st = cm.status()
        print(f"  Tip: {st['tip']}")

    elif args.command == "append":
        cm.load()
        block = cm.append_block(args.adr_id)
        print(f"Block {block.block_number} appended for {block.adr_id}")
        print(f"  Content hash: {block.content_hash[:32]}...")
        print(f"  Block hash:   {block.block_hash[:32]}...")

    elif args.command == "sign":
        cm.load()
        sig = cm.sign_block(args.adr_id, args.signer)
        print(f"Block for {args.adr_id} signed by {sig.signer_id} (role: {sig.role})")

    elif args.command == "verify":
        cm.load()
        report = cm.verify_chain()
        print_report(report)
        sys.exit(0 if report["chain_valid"] else 1)

    elif args.command == "status":
        st = cm.status()
        if not st["initialized"]:
            print("Chain not initialized. Run: adr chain init")
            return
        print(f"Chain Status:")
        print(f"  Version:  {st['version']}")
        print(f"  Height:   {st['height']} blocks")
        print(f"  Tip:      {st['tip']}")
        print(f"  Last ADR: {st['last_block']['adr_id']} ({st['last_block']['timestamp']})")
        print(f"  Signed:   {st['signed_blocks']}/{st['height']} blocks")

    elif args.command == "show":
        cm.load()
        # Try as ADR ID first, then as block number
        block = cm.get_block_by_adr(args.adr_id)
        if block is None:
            try:
                block = cm.get_block(int(args.adr_id))
            except ValueError:
                pass
        if block is None:
            print(f"Block not found: {args.adr_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(block.to_dict(), indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
