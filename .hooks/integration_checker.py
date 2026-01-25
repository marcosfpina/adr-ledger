#!/usr/bin/env python3
"""
Integration Checker - Verify Feature Integration
================================================
Verifies that detected features are properly integrated:
- Has tests
- Is documented
- Has ADR if architectural
- Is visible in feature index

Usage:
    python3 integration_checker.py --feature-log .feature_tracking.json

STF Compliance: STF-C004 (Ghost Feature Prevention)
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class IntegrationStatus:
    """Integration status for a feature"""
    feature_name: str
    has_tests: bool
    has_documentation: bool
    has_adr: bool
    in_feature_index: bool
    is_integrated: bool

    def to_dict(self):
        return {
            'feature_name': self.feature_name,
            'has_tests': self.has_tests,
            'has_documentation': self.has_documentation,
            'has_adr': self.has_adr,
            'in_feature_index': self.in_feature_index,
            'is_integrated': self.is_integrated
        }


class IntegrationChecker:
    """Checks if features are properly integrated"""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def check_feature(self, feature: Dict) -> IntegrationStatus:
        """Check integration status of a feature"""
        feature_name = feature.get('name', '')
        feature_file = feature.get('file', '')

        # Check for tests
        has_tests = self._check_tests(feature_name, feature_file)

        # Check for documentation
        has_documentation = self._check_documentation(feature_name)

        # Check for ADR
        has_adr = self._check_adr(feature_name)

        # Check feature index
        in_feature_index = self._check_feature_index(feature_name)

        # Feature is integrated if it meets minimum requirements
        is_integrated = has_documentation or has_tests

        return IntegrationStatus(
            feature_name=feature_name,
            has_tests=has_tests,
            has_documentation=has_documentation,
            has_adr=has_adr,
            in_feature_index=in_feature_index,
            is_integrated=is_integrated
        )

    def _check_tests(self, feature_name: str, feature_file: str) -> bool:
        """Check if feature has tests"""
        # Common test patterns
        test_patterns = [
            f"test_{feature_name.lower()}",
            f"{feature_name.lower()}_test",
            f"test*{feature_name.lower()}*"
        ]

        # Check for test directory
        test_dirs = ['tests/', 'test/', '__tests__/']

        for test_dir in test_dirs:
            test_path = self.repo_root / test_dir
            if test_path.exists():
                for pattern in test_patterns:
                    result = subprocess.run(
                        ['find', str(test_path), '-iname', f'*{pattern}*'],
                        capture_output=True,
                        text=True
                    )
                    if result.stdout.strip():
                        return True

        # Check for tests in same directory as feature
        if feature_file:
            feature_path = Path(feature_file)
            test_file = feature_path.parent / f"test_{feature_path.stem}.py"
            if (self.repo_root / test_file).exists():
                return True

        return False

    def _check_documentation(self, feature_name: str) -> bool:
        """Check if feature is documented"""
        doc_files = [
            'README.md',
            'CHANGELOG.md',
            'docs/README.md',
            'FEATURES.md'
        ]

        feature_lower = feature_name.lower()

        for doc_file in doc_files:
            doc_path = self.repo_root / doc_file
            if doc_path.exists():
                try:
                    content = doc_path.read_text().lower()
                    if feature_lower in content:
                        return True
                except Exception:
                    pass

        return False

    def _check_adr(self, feature_name: str) -> bool:
        """Check if feature has an ADR"""
        adr_dirs = ['adr/', 'docs/adr/', 'architecture/']

        feature_lower = feature_name.lower()

        for adr_dir in adr_dirs:
            adr_path = self.repo_root / adr_dir
            if adr_path.exists():
                for adr_file in adr_path.rglob('*.md'):
                    try:
                        content = adr_file.read_text().lower()
                        if feature_lower in content:
                            return True
                    except Exception:
                        pass

        return False

    def _check_feature_index(self, feature_name: str) -> bool:
        """Check if feature is in feature index"""
        index_files = [
            'FEATURES.md',
            '.features.json',
            'features/index.md'
        ]

        feature_lower = feature_name.lower()

        for index_file in index_files:
            index_path = self.repo_root / index_file
            if index_path.exists():
                try:
                    content = index_path.read_text().lower()
                    if feature_lower in content:
                        return True
                except Exception:
                    pass

        return False


def load_feature_log(log_path: Path) -> List[Dict]:
    """Load feature log"""
    if not log_path.exists():
        return []

    try:
        with open(log_path, 'r') as f:
            data = json.load(f)
            return data.get('features', [])
    except Exception as e:
        print(f"Error loading feature log: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Check feature integration status')
    parser.add_argument(
        '--feature-log',
        default='.feature_tracking.json',
        help='Feature tracking log path'
    )
    parser.add_argument(
        '--fail-on-unintegrated',
        action='store_true',
        help='Exit with error code if unintegrated features found'
    )

    args = parser.parse_args()

    # Get repo root
    repo_root = Path(subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip())

    log_path = repo_root / args.feature_log

    # Load features
    features = load_feature_log(log_path)

    if not features:
        print("No features to check")
        return

    # Check integration
    checker = IntegrationChecker(repo_root)

    print("=" * 70)
    print("Feature Integration Report")
    print("=" * 70)
    print()

    unintegrated_features = []

    for feature in features:
        status = checker.check_feature(feature)

        # Print status
        integrated_icon = "✓" if status.is_integrated else "✗"
        print(f"{integrated_icon} {status.feature_name}")
        print(f"    Tests:         {'✓' if status.has_tests else '✗'}")
        print(f"    Documentation: {'✓' if status.has_documentation else '✗'}")
        print(f"    ADR:           {'✓' if status.has_adr else '✗'}")
        print(f"    Feature Index: {'✓' if status.in_feature_index else '✗'}")
        print()

        if not status.is_integrated:
            unintegrated_features.append(status)

    # Summary
    total = len(features)
    integrated = len([f for f in features if checker.check_feature(f).is_integrated])

    print("=" * 70)
    print(f"Summary: {integrated}/{total} features integrated ({integrated/total*100:.1f}%)")
    print("=" * 70)

    if unintegrated_features:
        print()
        print("⚠ Unintegrated features detected:")
        for feature in unintegrated_features:
            print(f"  - {feature.feature_name}")

        if args.fail_on_unintegrated:
            exit(1)

    exit(0)


if __name__ == '__main__':
    main()
