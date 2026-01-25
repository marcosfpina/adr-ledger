#!/usr/bin/env python3
"""
Feature Detector - Automated Feature Discovery
==============================================
Analyzes git commits to detect new features and verify documentation.

Usage:
    python3 feature_detector.py --commit <hash> --files <files> [--log <path>]

Features detected:
    - New functions/classes (high-level additions)
    - New API endpoints
    - New CLI commands
    - New configuration options
    - Significant architectural changes

STF Compliance: STF-C004 (Ghost Feature Prevention)
"""

import argparse
import json
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class Feature:
    """Detected feature"""
    name: str
    type: str  # 'function', 'class', 'endpoint', 'command', 'config'
    file: str
    line: int
    commit: str
    confidence: float
    documented: bool
    timestamp: str

    def to_dict(self):
        return asdict(self)


class FeatureDetector:
    """Detects features from git commits"""

    # Patterns for feature detection
    PATTERNS = {
        'function': [
            (r'^def\s+(\w+)\s*\(', 0.9),  # Python function
            (r'function\s+(\w+)\s*\(', 0.9),  # JavaScript function
            (r'fn\s+(\w+)\s*\(', 0.9),  # Rust function
        ],
        'class': [
            (r'^class\s+(\w+)', 0.95),  # Python/JS class
            (r'struct\s+(\w+)', 0.9),  # Rust/C struct
        ],
        'endpoint': [
            (r'@app\.(get|post|put|delete|patch)\(["\']([^"\']+)', 0.95),  # FastAPI/Flask
            (r'router\.(get|post|put|delete|patch)\(["\']([^"\']+)', 0.95),  # Express
        ],
        'command': [
            (r'cmd_(\w+)\s*\(', 0.9),  # CLI command pattern
            (r'@click\.command\(\)', 0.95),  # Click command
            (r'parser\.add_subparsers.*name=["\'](\w+)', 0.9),  # argparse subcommand
        ],
        'config': [
            (r'config\[(["\'])(\w+)\1\]', 0.8),  # Config key access
            (r'ENV\[(["\'])(\w+)\1\]', 0.85),  # Environment variable
        ]
    }

    # Documentation keywords
    DOC_KEYWORDS = [
        'README', 'CHANGELOG', 'doc/', 'docs/', '.md',
        'ADR', 'adr/', 'feature', 'TODO'
    ]

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def analyze_commit(
        self,
        commit_hash: str,
        changed_files: List[str],
        min_confidence: float = 0.7
    ) -> List[Feature]:
        """
        Analyze a commit for new features.

        Args:
            commit_hash: Git commit hash
            changed_files: List of changed file paths
            min_confidence: Minimum confidence threshold

        Returns:
            List of detected features
        """
        features = []

        for file_path in changed_files:
            # Skip non-code files
            if not self._is_code_file(file_path):
                continue

            # Get diff for file
            diff = self._get_file_diff(commit_hash, file_path)
            if not diff:
                continue

            # Analyze additions
            additions = self._extract_additions(diff)

            # Detect features in additions
            file_features = self._detect_features(
                additions,
                file_path,
                commit_hash
            )

            # Filter by confidence
            file_features = [
                f for f in file_features
                if f.confidence >= min_confidence
            ]

            features.extend(file_features)

        # Check documentation
        self._check_documentation(features, changed_files)

        return features

    def _is_code_file(self, path: str) -> bool:
        """Check if file is a code file"""
        code_extensions = [
            '.py', '.js', '.ts', '.rs', '.go', '.java',
            '.c', '.cpp', '.h', '.sh', '.bash'
        ]
        return any(path.endswith(ext) for ext in code_extensions)

    def _get_file_diff(self, commit_hash: str, file_path: str) -> Optional[str]:
        """Get diff for a specific file in commit"""
        try:
            result = subprocess.run(
                ['git', 'show', f'{commit_hash}:{file_path}'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout
        except Exception as e:
            print(f"Error getting diff for {file_path}: {e}")

        return None

    def _extract_additions(self, diff: str) -> List[Tuple[int, str]]:
        """Extract added lines from diff with line numbers"""
        additions = []
        current_line = 1

        for line in diff.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                # Added line
                additions.append((current_line, line[1:].strip()))
            if not line.startswith('-'):
                current_line += 1

        return additions

    def _detect_features(
        self,
        lines: List[Tuple[int, str]],
        file_path: str,
        commit_hash: str
    ) -> List[Feature]:
        """Detect features from code lines"""
        features = []

        for line_num, line in lines:
            for feature_type, patterns in self.PATTERNS.items():
                for pattern, confidence in patterns:
                    match = re.search(pattern, line)
                    if match:
                        # Extract feature name
                        if feature_type == 'endpoint':
                            name = f"{match.group(1).upper()} {match.group(2)}"
                        else:
                            name = match.group(1) if match.groups() else "unknown"

                        features.append(Feature(
                            name=name,
                            type=feature_type,
                            file=file_path,
                            line=line_num,
                            commit=commit_hash,
                            confidence=confidence,
                            documented=False,  # Will be checked later
                            timestamp=datetime.now().isoformat()
                        ))

        return features

    def _check_documentation(
        self,
        features: List[Feature],
        changed_files: List[str]
    ):
        """Check if features are documented in changed files"""
        # Check if any documentation files were changed
        doc_files_changed = any(
            any(keyword in f for keyword in self.DOC_KEYWORDS)
            for f in changed_files
        )

        if doc_files_changed:
            # Assume documented if doc files were modified
            for feature in features:
                feature.documented = True
        else:
            # Check commit message for documentation keywords
            try:
                commit_msg = subprocess.run(
                    ['git', 'log', '-1', '--pretty=%B'],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    timeout=5
                ).stdout.lower()

                if any(kw.lower() in commit_msg for kw in ['doc', 'readme', 'adr', 'changelog']):
                    for feature in features:
                        feature.documented = True
            except Exception:
                pass


def load_feature_log(log_path: Path) -> Dict:
    """Load existing feature log"""
    if log_path.exists():
        try:
            with open(log_path, 'r') as f:
                return json.load(f)
        except Exception:
            pass

    return {"version": "1.0", "features": []}


def save_feature_log(log_path: Path, data: Dict):
    """Save feature log"""
    try:
        with open(log_path, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving feature log: {e}")


def main():
    parser = argparse.ArgumentParser(description='Detect features in git commits')
    parser.add_argument('--commit', required=True, help='Commit hash')
    parser.add_argument('--files', required=True, help='Changed files (space-separated)')
    parser.add_argument('--log', default='.feature_tracking.json', help='Feature log path')
    parser.add_argument('--min-confidence', type=float, default=0.7, help='Min confidence')

    args = parser.parse_args()

    # Parse files
    changed_files = args.files.split()

    # Get repo root
    repo_root = Path(subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip())

    # Detect features
    detector = FeatureDetector(repo_root)
    features = detector.analyze_commit(
        args.commit,
        changed_files,
        args.min_confidence
    )

    # Load existing log
    log_path = repo_root / args.log
    feature_log = load_feature_log(log_path)

    # Output results
    if features:
        print("FEATURE_DETECTED")
        print()
        for feature in features:
            print(f"Feature: {feature.name}")
            print(f"  Type: {feature.type}")
            print(f"  File: {feature.file}:{feature.line}")
            print(f"  Confidence: {feature.confidence:.2%}")
            print(f"  Documented: {'✓' if feature.documented else '✗'}")
            if not feature.documented:
                print("  Status: UNDOCUMENTED")
            print()

            # Add to log
            feature_log['features'].append(feature.to_dict())

        # Save log
        save_feature_log(log_path, feature_log)

        # Exit with code indicating undocumented features
        if any(not f.documented for f in features):
            exit(2)  # Warning code
    else:
        print("No features detected")

    exit(0)


if __name__ == '__main__':
    main()
