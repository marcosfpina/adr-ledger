"""
ADR-Ledger Supply Chain SBOM & Dependency Inventory

Decision-aware Software Bill of Materials that enriches Nix's
deterministic dependency pinning with governance context:
which ADR justified each dependency, who approved it, when it changed.

Exports to CycloneDX 1.6 using properties[] for ADR references.
"""

import argparse
import glob
import hashlib
import json
import re
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from crypto import compute_content_hash, sign_message, verify_signature, Signature

CHAIN_DIR = Path(__file__).parent
REPO_ROOT = CHAIN_DIR.parent
SBOM_DIR = CHAIN_DIR / "sbom"
SBOM_CURRENT = SBOM_DIR / "sbom_current.json"
SBOM_HISTORY = SBOM_DIR / "history"
FLAKE_LOCK = REPO_ROOT / "flake.lock"
FLAKE_NIX = REPO_ROOT / "flake.nix"


# ── Bootstrap ADR Map ────────────────────────────────────────────────────────

_BOOTSTRAP_ADR_MAP = {
    "nixpkgs":          {"adr": "ADR-0005", "justification": "NixOS como base declarativa"},
    "flake-utils":      {"adr": "ADR-0005", "justification": "Nix flake multi-system"},
    "pyyaml":           {"adr": "ADR-0006", "justification": "YAML frontmatter parsing"},
    "pynacl":           {"adr": "ADR-0032", "justification": "Ed25519 para decision chain"},
    "jsonschema":       {"adr": "ADR-0006", "justification": "Schema validation"},
    "check-jsonschema": {"adr": "ADR-0006", "justification": "CLI schema validation"},
    "yamllint":         {"adr": "ADR-0006", "justification": "YAML governance validation"},
    "jq":               {"adr": "ADR-0006", "justification": "JSON processing"},
    "graphviz":         {"adr": "ADR-0006", "justification": "Knowledge graph visualization"},
    "git":              {"adr": "ADR-0001", "justification": "Git como sistema operacional"},
}


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SBOMComponent:
    name: str               # "nixpkgs", "pyyaml", "jq"
    version: str            # rev hash, "nixpkgs-unstable", etc.
    type: str               # nix-input | python-pkg | system-tool | internal-module
    purl: str               # pkg:github/NixOS/nixpkgs@rev, pkg:pypi/pyyaml
    hash: str               # SHA256 (narHash for nix, file hash for internals)
    license: str            # "MIT", "unknown"
    source: str             # flake.lock | flake.nix | chain
    adr_reference: str      # ADR-XXXX that justifies this dep
    adr_justification: str  # Brief justification text
    first_seen: str         # ISO 8601
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SBOMManifest:
    version: str            # "1.0"
    format: str             # "adr-ledger-sbom-1.0"
    serial_number: str      # urn:uuid:...
    timestamp: str
    components: List[SBOMComponent]
    metadata: Dict[str, Any]
    sbom_hash: str          # SHA256 of canonical component list
    signature: Optional[dict]
    previous_sbom_hash: str  # Chain link to previous SBOM

    def to_dict(self) -> dict:
        d = {
            "version": self.version,
            "format": self.format,
            "serial_number": self.serial_number,
            "timestamp": self.timestamp,
            "components": [asdict(c) for c in self.components],
            "metadata": self.metadata,
            "sbom_hash": self.sbom_hash,
            "signature": self.signature,
            "previous_sbom_hash": self.previous_sbom_hash,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SBOMManifest":
        components = [SBOMComponent(**c) for c in d.get("components", [])]
        return cls(
            version=d["version"],
            format=d["format"],
            serial_number=d["serial_number"],
            timestamp=d["timestamp"],
            components=components,
            metadata=d.get("metadata", {}),
            sbom_hash=d["sbom_hash"],
            signature=d.get("signature"),
            previous_sbom_hash=d.get("previous_sbom_hash", "0" * 64),
        )


# ── SBOM Manager ─────────────────────────────────────────────────────────────

class SBOMManager:
    """Manages the decision-aware Software Bill of Materials."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or REPO_ROOT
        self.chain_dir = self.repo_root / ".chain"
        self.sbom_dir = self.chain_dir / "sbom"
        self.sbom_current = self.sbom_dir / "sbom_current.json"
        self.sbom_history = self.sbom_dir / "history"
        self.flake_lock = self.repo_root / "flake.lock"
        self.flake_nix = self.repo_root / "flake.nix"

        self.sbom_dir.mkdir(parents=True, exist_ok=True)
        self.sbom_history.mkdir(parents=True, exist_ok=True)

    # ── ADR Map ──────────────────────────────────────────────────────────

    def _load_adr_map(self) -> Dict[str, dict]:
        """Build dep→ADR map from bootstrap + ADR frontmatter scan."""
        adr_map = dict(_BOOTSTRAP_ADR_MAP)

        # Scan ADR frontmatter for supply_chain.dependencies_introduced
        adr_root = self.repo_root / "adr"
        fm_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

        for status_dir in ["accepted", "proposed"]:
            d = adr_root / status_dir
            if not d.exists():
                continue
            for md in sorted(d.glob("ADR-*.md")):
                content = md.read_text()
                match = fm_re.match(content)
                if not match:
                    continue
                try:
                    import yaml
                    fm = yaml.safe_load(match.group(1)) or {}
                except Exception:
                    continue

                adr_id = fm.get("id", "")
                sc = fm.get("supply_chain", {})
                for dep in sc.get("dependencies_introduced", []):
                    name = dep.get("name", "")
                    if name:
                        adr_map[name] = {
                            "adr": adr_id,
                            "justification": dep.get("justification", ""),
                        }

        return adr_map

    def _get_adr_info(self, name: str, adr_map: dict) -> tuple:
        """Return (adr_reference, justification) for a dependency."""
        info = adr_map.get(name, {})
        return (
            info.get("adr", "UNTRACKED"),
            info.get("justification", ""),
        )

    # ── Scanners ─────────────────────────────────────────────────────────

    def scan_nix_inputs(self, adr_map: dict) -> List[SBOMComponent]:
        """Parse flake.lock JSON, extract nix inputs."""
        if not self.flake_lock.exists():
            return []

        lock = json.loads(self.flake_lock.read_text())
        nodes = lock.get("nodes", {})
        root_inputs = nodes.get("root", {}).get("inputs", {})
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        components = []

        for input_name, node_key in root_inputs.items():
            node = nodes.get(node_key, {})
            locked = node.get("locked", {})
            original = node.get("original", {})

            rev = locked.get("rev", "unknown")
            nar_hash = locked.get("narHash", "")
            owner = locked.get("owner", original.get("owner", ""))
            repo = locked.get("repo", original.get("repo", ""))
            ref = original.get("ref", "")

            version = ref if ref else rev[:12]
            purl = f"pkg:github/{owner}/{repo}@{rev}" if owner and repo else f"pkg:nix/{input_name}"

            adr_ref, justification = self._get_adr_info(input_name, adr_map)

            components.append(SBOMComponent(
                name=input_name,
                version=version,
                type="nix-input",
                purl=purl,
                hash=nar_hash,
                license="MIT",
                source="flake.lock",
                adr_reference=adr_ref,
                adr_justification=justification,
                first_seen=now,
                metadata={"owner": owner, "repo": repo, "rev": rev},
            ))

            # Scan transitive inputs (one level)
            sub_inputs = node.get("inputs", {})
            for sub_name, sub_key in sub_inputs.items():
                if sub_key in root_inputs.values():
                    continue  # Already captured as root input
                sub_node = nodes.get(sub_key, {})
                sub_locked = sub_node.get("locked", {})
                sub_rev = sub_locked.get("rev", "unknown")
                sub_nar = sub_locked.get("narHash", "")
                sub_owner = sub_locked.get("owner", "")
                sub_repo = sub_locked.get("repo", "")
                sub_purl = f"pkg:github/{sub_owner}/{sub_repo}@{sub_rev}" if sub_owner else f"pkg:nix/{sub_name}"

                adr_ref_sub, just_sub = self._get_adr_info(sub_name, adr_map)

                components.append(SBOMComponent(
                    name=sub_name,
                    version=sub_rev[:12] if sub_rev != "unknown" else "unknown",
                    type="nix-input",
                    purl=sub_purl,
                    hash=sub_nar,
                    license="MIT",
                    source="flake.lock",
                    adr_reference=adr_ref_sub if adr_ref_sub != "UNTRACKED" else adr_ref,
                    adr_justification=just_sub or f"Transitive dependency of {input_name}",
                    first_seen=now,
                    metadata={"owner": sub_owner, "repo": sub_repo, "rev": sub_rev, "parent": input_name},
                ))

        return components

    def scan_python_deps(self, adr_map: dict) -> List[SBOMComponent]:
        """Scan flake.nix for pythonPackages.X references."""
        if not self.flake_nix.exists():
            return []

        content = self.flake_nix.read_text()
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        components = []
        seen = set()

        # Match pythonPackages.X and ps.X patterns
        patterns = [
            re.compile(r'pythonPackages\.(\w+)'),
            re.compile(r'ps\.(\w+)'),
        ]

        for pat in patterns:
            for match in pat.finditer(content):
                name = match.group(1)
                if name in seen or name in ("buildPythonApplication", "buildPythonPackage"):
                    continue
                seen.add(name)

                adr_ref, justification = self._get_adr_info(name, adr_map)

                components.append(SBOMComponent(
                    name=name,
                    version="nixpkgs-pinned",
                    type="python-pkg",
                    purl=f"pkg:pypi/{name}",
                    hash="",
                    license="unknown",
                    source="flake.nix",
                    adr_reference=adr_ref,
                    adr_justification=justification,
                    first_seen=now,
                ))

        return components

    def scan_system_tools(self, adr_map: dict) -> List[SBOMComponent]:
        """Scan flake.nix for pkgs.X in devShell buildInputs."""
        if not self.flake_nix.exists():
            return []

        content = self.flake_nix.read_text()
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        components = []
        seen = set()

        # Match pkgs.X (but exclude pkgs.lib, pkgs.mkShell, pkgs.runCommand, etc.)
        infra_names = {"lib", "mkShell", "runCommand", "writeShellScriptBin", "writeShellScript",
                       "bash", "system", "legacyPackages", "python313"}
        for match in re.finditer(r'(?<![.\w])pkgs\.([\w][\w-]*)', content):
            name = match.group(1)
            if name in seen or name in infra_names:
                continue
            seen.add(name)

            adr_ref, justification = self._get_adr_info(name, adr_map)

            components.append(SBOMComponent(
                name=name,
                version="nixpkgs-pinned",
                type="system-tool",
                purl=f"pkg:nix/{name}",
                hash="",
                license="unknown",
                source="flake.nix",
                adr_reference=adr_ref,
                adr_justification=justification,
                first_seen=now,
            ))

        return components

    def scan_internal_modules(self, adr_map: dict) -> List[SBOMComponent]:
        """Scan .chain/*.py modules."""
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        components = []

        for py_file in sorted(self.chain_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue

            content = py_file.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            module_name = py_file.stem

            adr_ref, justification = self._get_adr_info(module_name, adr_map)
            # All chain modules are justified by ADR-0032 if not explicitly mapped
            if adr_ref == "UNTRACKED":
                adr_ref = "ADR-0032"
                justification = f"Chain module: {module_name}"

            components.append(SBOMComponent(
                name=module_name,
                version=file_hash[:12],
                type="internal-module",
                purl=f"pkg:adr-ledger/.chain/{py_file.name}",
                hash=file_hash,
                license="MIT",
                source="chain",
                adr_reference=adr_ref,
                adr_justification=justification,
                first_seen=now,
                metadata={"path": str(py_file.relative_to(self.repo_root)), "size": len(content)},
            ))

        return components

    # ── Core Operations ──────────────────────────────────────────────────

    def _compute_sbom_hash(self, components: List[SBOMComponent]) -> str:
        """Compute canonical hash of the component list."""
        canonical_parts = []
        for c in sorted(components, key=lambda x: (x.type, x.name)):
            canonical_parts.append(f"{c.type}:{c.name}:{c.version}:{c.hash}")
        canonical = "|".join(canonical_parts)
        return compute_content_hash(canonical)

    def _get_previous_hash(self) -> str:
        """Get hash from current SBOM (which becomes previous)."""
        if self.sbom_current.exists():
            try:
                data = json.loads(self.sbom_current.read_text())
                return data.get("sbom_hash", "0" * 64)
            except (json.JSONDecodeError, KeyError):
                pass
        return "0" * 64

    def generate(self, signer_name: Optional[str] = None) -> SBOMManifest:
        """Generate a new SBOM from all sources."""
        adr_map = self._load_adr_map()

        # Run all scanners
        components = []
        components.extend(self.scan_nix_inputs(adr_map))
        components.extend(self.scan_python_deps(adr_map))
        components.extend(self.scan_system_tools(adr_map))
        components.extend(self.scan_internal_modules(adr_map))

        # Deduplicate by (type, name)
        seen = set()
        deduped = []
        for c in components:
            key = (c.type, c.name)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        components = deduped

        # Archive current if it exists
        previous_hash = self._get_previous_hash()
        if self.sbom_current.exists():
            try:
                old = json.loads(self.sbom_current.read_text())
                old_ts = old.get("timestamp", "unknown").replace(":", "")
                archive_name = f"sbom_{old_ts}.json"
                archive_path = self.sbom_history / archive_name
                if not archive_path.exists():
                    archive_path.write_text(json.dumps(old, indent=2) + "\n")
            except (json.JSONDecodeError, KeyError):
                pass

        sbom_hash = self._compute_sbom_hash(components)

        manifest = SBOMManifest(
            version="1.0",
            format="adr-ledger-sbom-1.0",
            serial_number=f"urn:uuid:{uuid.uuid4()}",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            components=components,
            metadata={
                "tool": "adr-ledger-sbom-manager",
                "repo": str(self.repo_root),
                "total_components": len(components),
                "by_type": {},
            },
            sbom_hash=sbom_hash,
            signature=None,
            previous_sbom_hash=previous_hash,
        )

        # Count by type
        for c in components:
            manifest.metadata["by_type"][c.type] = manifest.metadata["by_type"].get(c.type, 0) + 1

        # Sign if requested
        if signer_name:
            sig = sign_message(sbom_hash, signer_name)
            manifest.signature = sig.to_dict()

        # Save
        self.sbom_current.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")

        return manifest

    def verify(self) -> dict:
        """Re-scan and compare with current SBOM. Returns drift report."""
        if not self.sbom_current.exists():
            return {"valid": False, "error": "No SBOM found. Run: sbom_manager.py generate"}

        current = SBOMManifest.from_dict(json.loads(self.sbom_current.read_text()))

        # Re-scan
        adr_map = self._load_adr_map()
        fresh_components = []
        fresh_components.extend(self.scan_nix_inputs(adr_map))
        fresh_components.extend(self.scan_python_deps(adr_map))
        fresh_components.extend(self.scan_system_tools(adr_map))
        fresh_components.extend(self.scan_internal_modules(adr_map))

        # Deduplicate
        seen = set()
        deduped = []
        for c in fresh_components:
            key = (c.type, c.name)
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        fresh_components = deduped

        fresh_hash = self._compute_sbom_hash(fresh_components)

        # Compare
        report = {
            "valid": True,
            "sbom_hash_match": fresh_hash == current.sbom_hash,
            "current_hash": current.sbom_hash[:16] + "...",
            "fresh_hash": fresh_hash[:16] + "...",
            "signature_valid": None,
            "drift": [],
            "errors": [],
        }

        if not report["sbom_hash_match"]:
            report["valid"] = False
            report["errors"].append("SBOM hash mismatch — dependency drift detected")

            # Compute diff
            current_set = {(c.type, c.name): c for c in current.components}
            fresh_set = {(c.type, c.name): c for c in fresh_components}

            for key in fresh_set:
                if key not in current_set:
                    report["drift"].append({"action": "added", "type": key[0], "name": key[1]})
            for key in current_set:
                if key not in fresh_set:
                    report["drift"].append({"action": "removed", "type": key[0], "name": key[1]})
            for key in current_set:
                if key in fresh_set:
                    if current_set[key].hash != fresh_set[key].hash and current_set[key].hash:
                        report["drift"].append({
                            "action": "modified",
                            "type": key[0],
                            "name": key[1],
                            "old_hash": current_set[key].hash[:16],
                            "new_hash": fresh_set[key].hash[:16],
                        })

        # Verify signature
        if current.signature:
            sig = Signature.from_dict(current.signature)
            report["signature_valid"] = verify_signature(current.sbom_hash, sig)
            if not report["signature_valid"]:
                report["valid"] = False
                report["errors"].append(f"Invalid signature from {sig.signer_id}")

        return report

    def diff(self, old_path: str, new_path: Optional[str] = None) -> dict:
        """Compare two SBOMs: added/removed/modified."""
        old_data = json.loads(Path(old_path).read_text())
        old_sbom = SBOMManifest.from_dict(old_data)

        if new_path:
            new_data = json.loads(Path(new_path).read_text())
        else:
            if not self.sbom_current.exists():
                return {"error": "No current SBOM to compare against"}
            new_data = json.loads(self.sbom_current.read_text())
        new_sbom = SBOMManifest.from_dict(new_data)

        old_set = {(c.type, c.name): c for c in old_sbom.components}
        new_set = {(c.type, c.name): c for c in new_sbom.components}

        added = []
        removed = []
        modified = []

        for key, comp in new_set.items():
            if key not in old_set:
                added.append({"type": comp.type, "name": comp.name, "version": comp.version})
            elif old_set[key].hash != comp.hash and comp.hash:
                modified.append({
                    "type": comp.type, "name": comp.name,
                    "old_version": old_set[key].version,
                    "new_version": comp.version,
                })

        for key, comp in old_set.items():
            if key not in new_set:
                removed.append({"type": comp.type, "name": comp.name, "version": comp.version})

        return {
            "old_timestamp": old_sbom.timestamp,
            "new_timestamp": new_sbom.timestamp,
            "added": added,
            "removed": removed,
            "modified": modified,
            "summary": f"+{len(added)} -{len(removed)} ~{len(modified)}",
        }

    def export_cyclonedx(self) -> dict:
        """Generate CycloneDX 1.6 JSON (no external lib needed)."""
        if not self.sbom_current.exists():
            return {"error": "No SBOM found. Run: sbom_manager.py generate"}

        sbom = SBOMManifest.from_dict(json.loads(self.sbom_current.read_text()))

        cdx_components = []
        for c in sbom.components:
            cdx_type = "library"
            if c.type == "system-tool":
                cdx_type = "application"
            elif c.type == "internal-module":
                cdx_type = "file"

            comp = {
                "type": cdx_type,
                "name": c.name,
                "version": c.version,
                "purl": c.purl,
                "properties": [
                    {"name": "adr:reference", "value": c.adr_reference},
                    {"name": "adr:justification", "value": c.adr_justification},
                    {"name": "adr:type", "value": c.type},
                    {"name": "adr:source", "value": c.source},
                ],
            }

            if c.hash:
                comp["hashes"] = [{"alg": "SHA-256", "content": c.hash}]

            if c.license and c.license != "unknown":
                comp["licenses"] = [{"license": {"id": c.license}}]

            cdx_components.append(comp)

        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "serialNumber": sbom.serial_number,
            "version": 1,
            "metadata": {
                "timestamp": sbom.timestamp,
                "tools": [{"name": "adr-ledger-sbom-manager", "version": "1.0"}],
                "properties": [
                    {"name": "adr:sbom_hash", "value": sbom.sbom_hash},
                    {"name": "adr:previous_sbom_hash", "value": sbom.previous_sbom_hash},
                ],
            },
            "components": cdx_components,
        }

    def show(self) -> dict:
        """Show current SBOM summary."""
        if not self.sbom_current.exists():
            return {"error": "No SBOM found. Run: sbom_manager.py generate"}
        return json.loads(self.sbom_current.read_text())

    def list_components(self, type_filter: Optional[str] = None) -> List[dict]:
        """List components with optional type filter."""
        if not self.sbom_current.exists():
            return []

        sbom = SBOMManifest.from_dict(json.loads(self.sbom_current.read_text()))
        result = []
        for c in sbom.components:
            if type_filter and c.type != type_filter:
                continue
            result.append({
                "name": c.name,
                "type": c.type,
                "version": c.version,
                "adr_reference": c.adr_reference,
                "source": c.source,
            })
        return result


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ADR-Ledger SBOM Manager")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen = sub.add_parser("generate", help="Generate SBOM from all sources")
    gen.add_argument("--signer", help="Sign the SBOM with this key")

    # verify
    sub.add_parser("verify", help="Verify SBOM integrity (detect drift)")

    # diff
    df = sub.add_parser("diff", help="Compare two SBOMs")
    df.add_argument("old", help="Path to old SBOM")
    df.add_argument("new", nargs="?", help="Path to new SBOM (default: current)")

    # export
    ex = sub.add_parser("export", help="Export as CycloneDX 1.6 JSON")
    ex.add_argument("-o", "--output", help="Output file (default: stdout)")

    # show
    sub.add_parser("show", help="Show current SBOM")

    # list-components
    lc = sub.add_parser("list-components", help="List SBOM components")
    lc.add_argument("--type", dest="comp_type", help="Filter by type")

    args = parser.parse_args()
    mgr = SBOMManager()

    if args.command == "generate":
        manifest = mgr.generate(signer_name=args.signer)
        print(f"SBOM generated: {len(manifest.components)} components")
        for ctype, count in manifest.metadata.get("by_type", {}).items():
            print(f"  {ctype}: {count}")
        print(f"  Hash:   {manifest.sbom_hash[:32]}...")
        print(f"  Signed: {'Yes' if manifest.signature else 'No'}")
        print(f"  Saved:  {mgr.sbom_current}")

    elif args.command == "verify":
        report = mgr.verify()
        if "error" in report:
            print(f"ERROR: {report['error']}", file=sys.stderr)
            sys.exit(1)

        print("SBOM Verification:")
        print(f"  Hash match:      {report['sbom_hash_match']}")
        print(f"  Signature valid: {report['signature_valid']}")
        print(f"  Overall:         {'VALID' if report['valid'] else 'INVALID'}")

        if report["drift"]:
            print(f"  Drift detected ({len(report['drift'])} changes):")
            for d in report["drift"]:
                print(f"    [{d['action']}] {d['type']}:{d['name']}")

        if report["errors"]:
            for err in report["errors"]:
                print(f"  ERROR: {err}")

        sys.exit(0 if report["valid"] else 1)

    elif args.command == "diff":
        result = mgr.diff(args.old, args.new)
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
            sys.exit(1)

        print(f"SBOM Diff: {result['summary']}")
        print(f"  Old: {result['old_timestamp']}")
        print(f"  New: {result['new_timestamp']}")

        if result["added"]:
            print("  Added:")
            for a in result["added"]:
                print(f"    + {a['type']}:{a['name']} ({a['version']})")
        if result["removed"]:
            print("  Removed:")
            for r in result["removed"]:
                print(f"    - {r['type']}:{r['name']} ({r['version']})")
        if result["modified"]:
            print("  Modified:")
            for m in result["modified"]:
                print(f"    ~ {m['type']}:{m['name']} ({m['old_version']} -> {m['new_version']})")

    elif args.command == "export":
        cdx = mgr.export_cyclonedx()
        if "error" in cdx:
            print(f"ERROR: {cdx['error']}", file=sys.stderr)
            sys.exit(1)

        output = json.dumps(cdx, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(output)
            print(f"CycloneDX exported to {args.output}")
        else:
            print(output)

    elif args.command == "show":
        data = mgr.show()
        if "error" in data:
            print(f"ERROR: {data['error']}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(data, indent=2))

    elif args.command == "list-components":
        components = mgr.list_components(type_filter=args.comp_type)
        if not components:
            print("No components found. Run: sbom_manager.py generate")
            return

        print(f"{'Name':25s}  {'Type':18s}  {'Version':15s}  {'ADR':10s}  {'Source'}")
        print("-" * 85)
        for c in components:
            print(f"{c['name']:25s}  {c['type']:18s}  {c['version']:15s}  {c['adr_reference']:10s}  {c['source']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
