#!/usr/bin/env python3
"""
ADR Parser - Transforms Architecture Decision Records into Knowledge Law

This parser reads YAML-frontmatter Markdown ADRs and transforms them into
structured knowledge that can be consumed by intelligent systems
(CEREBRO, SPECTRE, PHANTOM, NEUTRON).

The output is "knowledge as law" - immutable, queryable, traversable.
"""

import os
import re
import json
import yaml
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# =============================================================================
# DATA MODELS
# =============================================================================

class ADRStatus(Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class Classification(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"


@dataclass
class Author:
    name: str
    role: Optional[str] = None
    github: Optional[str] = None


@dataclass
class Risk:
    risk: str
    probability: str  # low, medium, high
    impact: str       # low, medium, high
    mitigation: Optional[str] = None


@dataclass
class Task:
    task: str
    owner: Optional[str] = None
    status: str = "todo"  # todo, in_progress, done, blocked


@dataclass
class Alternative:
    option: str
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    why_rejected: Optional[str] = None


@dataclass
class ChangelogEntry:
    date: str
    author: str
    change: str
    commit_hash: Optional[str] = None


@dataclass
class ADRNode:
    """
    Represents a parsed ADR as a knowledge node.
    This is the canonical representation for agent consumption.
    """
    # Identity
    id: str
    title: str
    status: ADRStatus
    date: str
    
    # Authorship
    authors: List[Author] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    
    # Governance
    classification: Optional[Classification] = None
    compliance_tags: List[str] = field(default_factory=list)
    requires_approval_from: List[str] = field(default_factory=list)
    
    # Scope
    projects: List[str] = field(default_factory=list)
    layers: List[str] = field(default_factory=list)
    environments: List[str] = field(default_factory=list)
    
    # Content (the actual knowledge)
    context: str = ""
    decision: str = ""
    consequences_positive: List[str] = field(default_factory=list)
    consequences_negative: List[str] = field(default_factory=list)
    risks: List[Risk] = field(default_factory=list)
    
    # Rationale
    drivers: List[str] = field(default_factory=list)
    alternatives: List[Alternative] = field(default_factory=list)
    trade_offs: List[str] = field(default_factory=list)
    
    # Implementation
    effort: Optional[str] = None
    timeline: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    
    # Relations (for knowledge graph)
    supersedes: List[str] = field(default_factory=list)
    superseded_by: Optional[str] = None
    related_to: List[str] = field(default_factory=list)
    enables: List[str] = field(default_factory=list)
    implements: List[str] = field(default_factory=list)
    
    # Knowledge extraction metadata
    keywords: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    questions_answered: List[str] = field(default_factory=list)
    embedding_priority: str = "normal"
    
    # Audit
    created_at: Optional[str] = None
    last_modified: Optional[str] = None
    version: int = 1
    changelog: List[ChangelogEntry] = field(default_factory=list)
    
    # Computed fields
    content_hash: Optional[str] = None
    file_path: Optional[str] = None
    
    def compute_hash(self) -> str:
        """Compute content hash for change detection."""
        content = f"{self.context}{self.decision}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, list) and value and isinstance(value[0], Enum):
                result[key] = [v.value for v in value]
            else:
                result[key] = value
        return result
    
    def to_knowledge_fragment(self) -> Dict[str, Any]:
        """
        Convert to a knowledge fragment for CEREBRO ingestion.
        This is the "law" representation - distilled, queryable truth.
        """
        return {
            "id": self.id,
            "type": "architecture_decision",
            "title": self.title,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "summary": self._generate_summary(),
            "scope": {
                "projects": self.projects,
                "layers": self.layers,
            },
            "knowledge": {
                "what": self.decision,
                "why": self.context,
                "implications": {
                    "positive": self.consequences_positive,
                    "negative": self.consequences_negative,
                },
                "alternatives_rejected": [a.option for a in self.alternatives],
            },
            "questions": self.questions_answered,
            "keywords": self.keywords,
            "concepts": self.concepts,
            "relations": {
                "supersedes": self.supersedes,
                "related": self.related_to,
                "enables": self.enables,
            },
            "governance": {
                "classification": self.classification.value if self.classification else None,
                "compliance": self.compliance_tags,
            },
            "metadata": {
                "date": self.date,
                "version": self.version,
                "hash": self.content_hash,
                "embedding_priority": self.embedding_priority,
            }
        }
    
    def _generate_summary(self) -> str:
        """Generate a one-line summary for quick reference."""
        return f"[{self.id}] {self.title}: {self.decision[:100]}..."


# =============================================================================
# PARSER
# =============================================================================

class ADRParser:
    """
    Parses ADR files (YAML frontmatter + Markdown body) into ADRNode objects.
    
    File format expected:
    ```
    ---
    id: ADR-0001
    title: Use Rust for SIEM Parser
    status: accepted
    ...
    ---
    
    ## Context
    ...
    
    ## Decision
    ...
    ```
    """
    
    FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)$', re.DOTALL)
    SECTION_PATTERN = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)
    
    def __init__(self, schema_path: Optional[str] = None):
        self.schema = None
        if schema_path and os.path.exists(schema_path):
            with open(schema_path) as f:
                self.schema = json.load(f)
    
    def parse_file(self, file_path: str) -> ADRNode:
        """Parse a single ADR file."""
        path = Path(file_path)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return self.parse_content(content, str(path))
    
    def parse_content(self, content: str, source_path: Optional[str] = None) -> ADRNode:
        """Parse ADR content string."""
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            raise ValueError(f"Invalid ADR format: missing YAML frontmatter")
        
        frontmatter_str = match.group(1)
        body = match.group(2)
        
        # Parse YAML frontmatter
        frontmatter = yaml.safe_load(frontmatter_str)
        
        # Parse Markdown sections
        sections = self._parse_sections(body)
        
        # Build ADRNode
        node = self._build_node(frontmatter, sections)
        node.file_path = source_path
        node.content_hash = node.compute_hash()
        
        return node
    
    def _parse_sections(self, body: str) -> Dict[str, str]:
        """Parse Markdown body into sections."""
        sections = {}
        parts = self.SECTION_PATTERN.split(body)
        
        # parts[0] is content before first header (usually empty)
        # parts[1::2] are header names
        # parts[2::2] are section contents
        
        for i in range(1, len(parts), 2):
            header = parts[i].lower().replace(' ', '_')
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[header] = content
        
        return sections
    
    def _build_node(self, fm: Dict[str, Any], sections: Dict[str, str]) -> ADRNode:
        """Build ADRNode from parsed data."""
        # Parse status
        status_str = fm.get('status', 'proposed')
        status = ADRStatus(status_str) if status_str in [s.value for s in ADRStatus] else ADRStatus.PROPOSED
        
        # Parse classification
        classification = None
        if 'governance' in fm and 'classification' in fm['governance']:
            cls_str = fm['governance']['classification']
            classification = Classification(cls_str) if cls_str in [c.value for c in Classification] else None
        
        # Parse authors
        authors = []
        for a in fm.get('authors', []):
            if isinstance(a, str):
                authors.append(Author(name=a))
            elif isinstance(a, dict):
                authors.append(Author(
                    name=a.get('name', 'Unknown'),
                    role=a.get('role'),
                    github=a.get('github')
                ))
        
        # Parse risks
        risks = []
        if 'consequences' in fm and 'risks' in fm['consequences']:
            for r in fm['consequences']['risks']:
                risks.append(Risk(
                    risk=r.get('risk', ''),
                    probability=r.get('probability', 'medium'),
                    impact=r.get('impact', 'medium'),
                    mitigation=r.get('mitigation')
                ))
        
        # Parse alternatives
        alternatives = []
        if 'rationale' in fm and 'alternatives_considered' in fm['rationale']:
            for alt in fm['rationale']['alternatives_considered']:
                alternatives.append(Alternative(
                    option=alt.get('option', ''),
                    pros=alt.get('pros', []),
                    cons=alt.get('cons', []),
                    why_rejected=alt.get('why_rejected')
                ))
        
        # Parse tasks
        tasks = []
        if 'implementation' in fm and 'tasks' in fm['implementation']:
            for t in fm['implementation']['tasks']:
                tasks.append(Task(
                    task=t.get('task', ''),
                    owner=t.get('owner'),
                    status=t.get('status', 'todo')
                ))
        
        # Parse changelog
        changelog = []
        if 'audit' in fm and 'changelog' in fm['audit']:
            for entry in fm['audit']['changelog']:
                changelog.append(ChangelogEntry(
                    date=entry.get('date', ''),
                    author=entry.get('author', ''),
                    change=entry.get('change', ''),
                    commit_hash=entry.get('commit_hash')
                ))
        
        return ADRNode(
            # Identity
            id=fm.get('id', 'ADR-0000'),
            title=fm.get('title', 'Untitled'),
            status=status,
            date=fm.get('date', datetime.now().strftime('%Y-%m-%d')),
            
            # Authorship
            authors=authors,
            reviewers=fm.get('reviewers', []),
            
            # Governance
            classification=classification,
            compliance_tags=fm.get('governance', {}).get('compliance_tags', []),
            requires_approval_from=fm.get('governance', {}).get('requires_approval_from', []),
            
            # Scope
            projects=fm.get('scope', {}).get('projects', []),
            layers=fm.get('scope', {}).get('layers', []),
            environments=fm.get('scope', {}).get('environments', []),
            
            # Content - prefer frontmatter, fallback to sections
            context=fm.get('context') or sections.get('context', ''),
            decision=fm.get('decision') or sections.get('decision', ''),
            consequences_positive=fm.get('consequences', {}).get('positive', []),
            consequences_negative=fm.get('consequences', {}).get('negative', []),
            risks=risks,
            
            # Rationale
            drivers=fm.get('rationale', {}).get('drivers', []),
            alternatives=alternatives,
            trade_offs=fm.get('rationale', {}).get('trade_offs', []),
            
            # Implementation
            effort=fm.get('implementation', {}).get('effort'),
            timeline=fm.get('implementation', {}).get('timeline'),
            dependencies=fm.get('implementation', {}).get('dependencies', []),
            blocked_by=fm.get('implementation', {}).get('blocked_by', []),
            tasks=tasks,
            
            # Relations
            supersedes=fm.get('relations', {}).get('supersedes', []),
            superseded_by=fm.get('relations', {}).get('superseded_by'),
            related_to=fm.get('relations', {}).get('related_to', []),
            enables=fm.get('relations', {}).get('enables', []),
            implements=fm.get('relations', {}).get('implements', []),
            
            # Knowledge extraction
            keywords=fm.get('knowledge_extraction', {}).get('keywords', []),
            concepts=fm.get('knowledge_extraction', {}).get('concepts', []),
            questions_answered=fm.get('knowledge_extraction', {}).get('questions_answered', []),
            embedding_priority=fm.get('knowledge_extraction', {}).get('embedding_priority', 'normal'),
            
            # Audit
            created_at=fm.get('audit', {}).get('created_at'),
            last_modified=fm.get('audit', {}).get('last_modified'),
            version=fm.get('audit', {}).get('version', 1),
            changelog=changelog,
        )
    
    def parse_directory(self, dir_path: str, recursive: bool = True) -> List[ADRNode]:
        """Parse all ADR files in a directory."""
        path = Path(dir_path)
        pattern = '**/*.md' if recursive else '*.md'
        
        nodes = []
        for file_path in path.glob(pattern):
            try:
                node = self.parse_file(str(file_path))
                nodes.append(node)
            except Exception as e:
                print(f"Warning: Failed to parse {file_path}: {e}")
        
        return nodes


# =============================================================================
# KNOWLEDGE TRANSFORMER
# =============================================================================

class KnowledgeTransformer:
    """
    Transforms parsed ADRs into various knowledge formats for agent consumption.
    """
    
    def __init__(self, nodes: List[ADRNode]):
        self.nodes = nodes
        self.index = {n.id: n for n in nodes}
    
    def to_knowledge_base(self) -> Dict[str, Any]:
        """
        Generate complete knowledge base for CEREBRO ingestion.
        This is the "Livro Razão" - the authoritative ledger.
        """
        return {
            "meta": {
                "type": "adr_knowledge_base",
                "version": "1.0",
                "generated_at": datetime.now().isoformat(),
                "total_decisions": len(self.nodes),
                "by_status": self._count_by_status(),
                "by_project": self._count_by_project(),
            },
            "decisions": [n.to_knowledge_fragment() for n in self.nodes],
            "graph": self._build_graph(),
            "concepts_index": self._build_concepts_index(),
            "questions_index": self._build_questions_index(),
        }
    
    def _count_by_status(self) -> Dict[str, int]:
        counts = {}
        for n in self.nodes:
            status = n.status.value if isinstance(n.status, Enum) else n.status
            counts[status] = counts.get(status, 0) + 1
        return counts
    
    def _count_by_project(self) -> Dict[str, int]:
        counts = {}
        for n in self.nodes:
            for p in n.projects:
                counts[p] = counts.get(p, 0) + 1
        return counts
    
    def _build_graph(self) -> Dict[str, Any]:
        """Build knowledge graph for traversal."""
        nodes = []
        edges = []
        
        for adr in self.nodes:
            nodes.append({
                "id": adr.id,
                "type": "adr",
                "label": adr.title,
                "status": adr.status.value if isinstance(adr.status, Enum) else adr.status,
                "projects": adr.projects,
            })
            
            # Supersedes edges
            for target in adr.supersedes:
                edges.append({
                    "source": adr.id,
                    "target": target,
                    "type": "supersedes"
                })
            
            # Related edges
            for target in adr.related_to:
                edges.append({
                    "source": adr.id,
                    "target": target,
                    "type": "related_to"
                })
            
            # Enables edges
            for target in adr.enables:
                edges.append({
                    "source": adr.id,
                    "target": target,
                    "type": "enables"
                })
            
            # Project membership
            for project in adr.projects:
                edges.append({
                    "source": adr.id,
                    "target": f"PROJECT:{project}",
                    "type": "belongs_to"
                })
        
        # Add project nodes
        projects = set()
        for n in self.nodes:
            projects.update(n.projects)
        for p in projects:
            nodes.append({
                "id": f"PROJECT:{p}",
                "type": "project",
                "label": p,
            })
        
        return {"nodes": nodes, "edges": edges}
    
    def _build_concepts_index(self) -> Dict[str, List[str]]:
        """Build concept → ADRs index."""
        index = {}
        for n in self.nodes:
            for concept in n.concepts:
                if concept not in index:
                    index[concept] = []
                index[concept].append(n.id)
        return index
    
    def _build_questions_index(self) -> Dict[str, str]:
        """Build question → ADR index for RAG retrieval."""
        index = {}
        for n in self.nodes:
            for question in n.questions_answered:
                index[question] = n.id
        return index
    
    def to_spectre_analysis_format(self) -> List[Dict[str, Any]]:
        """Format for SPECTRE sentiment/pattern analysis."""
        return [
            {
                "id": n.id,
                "text": f"{n.context}\n\n{n.decision}",
                "metadata": {
                    "type": "architecture_decision",
                    "status": n.status.value if isinstance(n.status, Enum) else n.status,
                    "date": n.date,
                    "classification": n.classification.value if n.classification else None,
                }
            }
            for n in self.nodes
        ]
    
    def to_phantom_training_format(self) -> List[Dict[str, Any]]:
        """Format for PHANTOM ML classification training."""
        return [
            {
                "features": {
                    "context_length": len(n.context),
                    "decision_length": len(n.decision),
                    "num_alternatives": len(n.alternatives),
                    "num_risks": len(n.risks),
                    "num_positive_consequences": len(n.consequences_positive),
                    "num_negative_consequences": len(n.consequences_negative),
                    "has_compliance_tags": len(n.compliance_tags) > 0,
                    "num_projects": len(n.projects),
                },
                "label": n.classification.value if n.classification else "unknown",
                "id": n.id,
            }
            for n in self.nodes
        ]


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ADR Parser - Transform Architecture Decisions into Knowledge Law'
    )
    parser.add_argument('path', help='Path to ADR file or directory')
    parser.add_argument('--output', '-o', default='stdout', help='Output file (default: stdout)')
    parser.add_argument('--format', '-f', choices=['json', 'knowledge', 'spectre', 'phantom', 'graph'],
                       default='json', help='Output format')
    parser.add_argument('--pretty', '-p', action='store_true', help='Pretty print JSON')
    parser.add_argument('--schema', '-s', help='Path to JSON schema for validation')
    
    args = parser.parse_args()
    
    adr_parser = ADRParser(schema_path=args.schema)
    
    path = Path(args.path)
    if path.is_file():
        nodes = [adr_parser.parse_file(str(path))]
    elif path.is_dir():
        nodes = adr_parser.parse_directory(str(path))
    else:
        print(f"Error: {path} not found")
        return 1
    
    transformer = KnowledgeTransformer(nodes)
    
    if args.format == 'json':
        output = [n.to_dict() for n in nodes]
    elif args.format == 'knowledge':
        output = transformer.to_knowledge_base()
    elif args.format == 'spectre':
        output = transformer.to_spectre_analysis_format()
    elif args.format == 'phantom':
        output = transformer.to_phantom_training_format()
    elif args.format == 'graph':
        output = transformer.to_knowledge_base()['graph']
    
    indent = 2 if args.pretty else None
    json_output = json.dumps(output, indent=indent, ensure_ascii=False, default=str)
    
    if args.output == 'stdout':
        print(json_output)
    else:
        with open(args.output, 'w') as f:
            f.write(json_output)
        print(f"Output written to {args.output}")
    
    return 0


if __name__ == '__main__':
    exit(main())
