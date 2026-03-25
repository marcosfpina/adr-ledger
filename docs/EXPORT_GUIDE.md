# ADR Export Guide

Complete guide for exporting Architecture Decision Records (ADRs) in JSON/JSONL format.

## Table of Contents

- [Overview](#overview)
- [Format Comparison](#format-comparison)
- [Filter Options](#filter-options)
- [Output Schema](#output-schema)
- [Integration Patterns](#integration-patterns)
- [Performance Considerations](#performance-considerations)
- [Troubleshooting](#troubleshooting)

## Overview

The `adr export` command exports ADRs as **knowledge fragments** - RAG-optimized representations designed for semantic search, machine learning, and knowledge graph applications.

### Key Features

- **Knowledge Fragments**: Not raw ADR dumps, but semantic extractions optimized for LLM ingestion
- **Filtering**: Status, project, classification, date range
- **Streaming**: JSONL format for constant-memory processing
- **Metadata**: Embedding priority, content hashing, relations graph
- **FAISS-Ready**: Compatible with vector databases and semantic search engines

## Format Comparison

### JSON Format

**Use Case**: Interactive exploration, small datasets (<100 ADRs), human-readable output

**Characteristics**:
- Single JSON array
- Pretty-printed by default (unless `--compact`)
- Requires loading entire file into memory
- Easy to manipulate with `jq`

**Example**:
```bash
adr export adr/accepted --format json > decisions.json
```

**Output Structure**:
```json
[
  {
    "id": "ADR-0001",
    "type": "architecture_decision",
    ...
  },
  {
    "id": "ADR-0002",
    ...
  }
]
```

### JSONL Format

**Use Case**: Pipeline ingestion, large datasets (>100 ADRs), streaming processing

**Characteristics**:
- One JSON object per line
- Streamable (constant memory)
- Line-by-line processing
- Ideal for ETL pipelines

**Example**:
```bash
adr export adr/accepted --format jsonl --compact > decisions.jsonl
```

**Output Structure**:
```jsonl
{"id": "ADR-0001", "type": "architecture_decision", ...}
{"id": "ADR-0002", "type": "architecture_decision", ...}
```

### Compact vs Pretty

| Option | Size | Use Case |
|--------|------|----------|
| Default (pretty) | Larger | Development, debugging, human reading |
| `--compact` | ~60% smaller | Production, pipelines, storage |

**Example Comparison**:
```bash
# Pretty (3.2MB)
adr export adr --format json > pretty.json

# Compact (1.2MB)
adr export adr --format json --compact > compact.json
```

## Filter Options

### Status Filter

Filter by ADR lifecycle status.

**Syntax**:
```bash
adr export <path> --filter-status <status>
```

**Valid Values**: `proposed`, `accepted`, `rejected`, `deprecated`, `superseded`

**Multiple Status**:
```bash
adr export adr --filter-status accepted --filter-status superseded
```

**Use Cases**:
- Export only accepted decisions for production knowledge base
- Analyze rejected alternatives for research
- Track deprecated decisions for migration planning

### Project Filter

Filter by project scope (OR logic).

**Syntax**:
```bash
adr export <path> --filter-project <project>
```

**Common Projects**: `CEREBRO`, `PHANTOM`, `SPECTRE`, `NEUTRON`, `GLOBAL`

**Multiple Projects** (OR logic):
```bash
adr export adr --filter-project CEREBRO --filter-project PHANTOM
```

This returns ADRs that belong to **CEREBRO** OR **PHANTOM** (not necessarily both).

**Use Cases**:
- Export PHANTOM-specific decisions for ML ingestion
- Generate project-specific documentation
- Audit cross-project dependencies

### Classification Filter

Filter by decision classification (severity/impact).

**Syntax**:
```bash
adr export <path> --filter-classification <class>
```

**Valid Values**: `critical`, `major`, `minor`, `patch`

**Use Cases**:
- Export critical decisions for security review
- Generate change logs by classification
- Prioritize knowledge base updates

### Date Range Filter

Filter by decision date (YYYY-MM-DD format).

**Syntax**:
```bash
adr export <path> --since YYYY-MM-DD --until YYYY-MM-DD
```

**Examples**:
```bash
# Decisions from 2026
adr export adr --since 2026-01-01 --until 2026-12-31

# Recent decisions (last 30 days)
adr export adr --since $(date -d '30 days ago' +%Y-%m-%d)

# Future decisions (proposed for next quarter)
adr export adr --filter-status proposed --since 2026-04-01
```

**Use Cases**:
- Generate quarterly architecture reports
- Track decision velocity over time
- Export recent changes for onboarding

### Combined Filters

All filters use **AND logic** when combined.

**Example**:
```bash
adr export adr \
  --filter-status accepted \
  --filter-project CEREBRO \
  --filter-classification major \
  --since 2026-01-01 \
  --format jsonl --compact
```

This returns ADRs that match **ALL** criteria:
- Status is `accepted` **AND**
- Project includes `CEREBRO` **AND**
- Classification is `major` **AND**
- Date >= 2026-01-01

## Output Schema

### Knowledge Fragment Structure

```typescript
interface KnowledgeFragment {
  // Identity
  id: string;                    // ADR-0001
  type: "architecture_decision";
  title: string;
  status: "proposed" | "accepted" | "rejected" | "deprecated" | "superseded";
  summary: string;               // One-line summary

  // Scope
  scope: {
    projects: string[];          // ["CEREBRO", "PHANTOM"]
    layers: string[];            // ["infrastructure", "ml"]
  };

  // Knowledge (RAG-Optimized)
  knowledge: {
    what: string;                // Decision text
    why: string;                 // Context/rationale
    implications: {
      positive: string[];
      negative: string[];
    };
    alternatives_rejected: string[];
  };

  // Semantic Enrichment
  questions: string[];           // Questions this ADR answers
  keywords: string[];            // Searchable keywords
  concepts: string[];            // High-level concepts

  // Relations (Knowledge Graph)
  relations: {
    supersedes: string[];        // ADRs this replaces
    related: string[];           // Related decisions
    enables: string[];           // ADRs this enables
  };

  // Governance
  governance: {
    classification: "critical" | "major" | "minor" | "patch";
    compliance: string[];        // ["LGPD", "SOC2"]
  };

  // Metadata
  metadata: {
    date: string;                // YYYY-MM-DD
    version: number;
    hash: string;                // Content hash (change detection)
    embedding_priority: "low" | "normal" | "high";
  };
}
```

### Field Descriptions

**`embedding_priority`**: Hints for semantic search engines
- `high`: Critical decisions, frequently queried
- `normal`: Standard decisions
- `low`: Historical, rarely queried

**`hash`**: SHA256 prefix for change detection
- Computed from `context` + `decision` fields
- Use to detect updates without full comparison

**`questions`**: Natural language queries this ADR answers
- Used for query-to-document matching
- Example: "Why did we choose NixOS?" → ADR-0001

**`relations`**: Knowledge graph edges
- `supersedes`: This ADR replaces older decisions
- `related`: Cross-references to related decisions
- `enables`: This ADR is a prerequisite for others

## Integration Patterns

### PHANTOM (Data Sanitizer)

PHANTOM processes ADRs into semantic chunks for FAISS indexing.

**Export**:
```bash
adr export adr/accepted --format jsonl --compact > /tmp/adr.jsonl
```

**Ingestion**:
```python
from phantom import CortexProcessor, FAISSVectorStore

# Load JSONL
with open('/tmp/adr.jsonl') as f:
    adrs = [json.loads(line) for line in f]

# Process each ADR
for adr in adrs:
    # Chunk semantic sections
    chunks = [
        {"text": adr["summary"], "type": "summary", "priority": "high"},
        {"text": adr["knowledge"]["why"], "type": "context", "priority": adr["metadata"]["embedding_priority"]},
        {"text": adr["knowledge"]["what"], "type": "decision", "priority": "critical"}
    ]

    # Embed
    embeddings = cortex.embed([c["text"] for c in chunks])

    # Index with metadata
    faiss_store.add_documents(
        chunks=chunks,
        embeddings=embeddings,
        metadata={
            "id": adr["id"],
            "status": adr["status"],
            "projects": adr["scope"]["projects"],
            "classification": adr["governance"]["classification"],
            "date": adr["metadata"]["date"]
        }
    )

# Save index
faiss_store.save("adr_ledger.faiss")
```

**Query**:
```python
# Semantic search with metadata filtering
results = faiss_store.search(
    query="Why NixOS?",
    top_k=5,
    filter={"status": "accepted", "projects": ["NEUTRON"]}
)
```

### CEREBRO (Air-Gapped Knowledge Vault)

CEREBRO maintains isolated, RAG-optimized knowledge bases.

**Export**:
```bash
adr export adr/accepted --format json --filter-status accepted > cerebro_kb.json
```

**Ingestion**:
```python
from cerebro import KnowledgeVault

vault = KnowledgeVault.load_or_create("adr_vault")

# Import ADRs
with open('cerebro_kb.json') as f:
    fragments = json.load(f)

for fragment in fragments:
    vault.add_decision(
        id=fragment["id"],
        content=fragment["knowledge"],
        metadata=fragment["metadata"],
        graph=fragment["relations"]
    )

# Query with graph traversal
response = vault.query("Explain our authentication strategy")
# Returns: Relevant ADRs + related decisions via graph
```

### External Tools

#### PostgreSQL + pgvector

```bash
# Export
adr export adr/accepted --format jsonl --compact > adr.jsonl

# Import to PostgreSQL
cat adr.jsonl | jq -c '{id: .id, content: .knowledge, meta: .metadata}' | \
  psql -c "COPY adr_knowledge (data) FROM STDIN WITH (FORMAT csv, QUOTE '\"');"
```

#### Elasticsearch

```bash
# Bulk index
cat adr.jsonl | \
  jq -c '{index: {_index: "adrs", _id: .id}}, .' | \
  curl -X POST http://localhost:9200/_bulk -H 'Content-Type: application/x-ndjson' --data-binary @-
```

#### Neo4j (Knowledge Graph)

```bash
# Export relations
adr export adr/accepted --format json | \
  jq -r '.[] | "\(.id),\(.relations.supersedes[]),supersedes"' | \
  cypher-shell --format plain
```

## Performance Considerations

### Memory Usage

| Operation | JSON | JSONL |
|-----------|------|-------|
| Parse 100 ADRs | ~5MB | ~5MB |
| Export 100 ADRs | ~10MB (array overhead) | ~2MB (streaming) |
| Large datasets (1000+) | Consider chunking | Constant memory |

### Export Speed

**Benchmarks** (12-core, 32GB RAM, NVMe):
- Parse 100 ADRs: ~2 seconds
- Export 100 ADRs (JSON): ~0.5 seconds
- Export 100 ADRs (JSONL): ~0.3 seconds
- Filter 1000 ADRs by status: ~0.1 seconds

### Optimization Strategies

**1. Use JSONL for large datasets**:
```bash
# Memory-efficient streaming
adr export adr --format jsonl --compact | \
  while read -r line; do
    process_adr "$line"
  done
```

**2. Filter early**:
```bash
# Export only what you need
adr export adr/accepted --filter-status accepted --filter-project PHANTOM
```

**3. Parallel processing**:
```bash
# Split by project and process in parallel
for project in CEREBRO PHANTOM SPECTRE; do
  adr export adr --filter-project $project --format jsonl --compact > ${project}.jsonl &
done
wait
```

## Troubleshooting

### Issue: Empty Result Set

**Symptom**:
```bash
adr export adr --filter-status accepted --filter-project NONEXISTENT
# Returns: []
```

**Solution**:
- Check filter values (case-sensitive)
- Verify projects exist in ADRs:
  ```bash
  adr export adr --format json | jq -r '.[].scope.projects[]' | sort -u
  ```

### Issue: Parse Errors

**Symptom**:
```
Warning: Failed to parse adr/proposed/ADR-0017.md: 'str' object has no attribute 'get'
```

**Cause**: ADR uses simplified YAML format (strings instead of objects)

**Solution**: Parser now supports both formats automatically. Update to latest version.

### Issue: Invalid JSONL

**Symptom**:
```bash
cat output.jsonl | jq .
# jq: parse error: Invalid numeric literal at line 2
```

**Cause**: Log messages mixed with JSON output

**Solution**: Redirect stderr:
```bash
adr export adr --format jsonl 2>/dev/null
```

### Issue: Slow Export

**Symptom**: Export takes >30 seconds for 100 ADRs

**Possible Causes**:
1. **Parsing overhead**: Use `--format jsonl` instead of `json`
2. **Large files**: ADRs with huge markdown content
3. **Disk I/O**: Slow filesystem

**Solution**:
```bash
# Profile with time
time adr export adr --format jsonl --compact > /dev/null

# Use tmpfs for temp files
export TMPDIR=/dev/shm
```

### Issue: Character Encoding

**Symptom**: Unicode characters garbled

**Solution**: Ensure UTF-8:
```bash
export LC_ALL=en_US.UTF-8
adr export adr --format json > output.json
```

## Advanced Use Cases

### Incremental Updates

Track ADR changes with content hashing:

```python
import json

# Load previous export
with open('prev_export.json') as f:
    prev = {adr['id']: adr['metadata']['hash'] for adr in json.load(f)}

# Export current state
with open('curr_export.json') as f:
    curr = {adr['id']: adr['metadata']['hash'] for adr in json.load(f)}

# Find changes
new_ids = set(curr.keys()) - set(prev.keys())
changed_ids = {id for id in curr if id in prev and curr[id] != prev[id]}
deleted_ids = set(prev.keys()) - set(curr.keys())

print(f"New: {len(new_ids)}, Changed: {len(changed_ids)}, Deleted: {len(deleted_ids)}")
```

### Custom Transformations

Extract specific fields with `jq`:

```bash
# Extract decision timeline
adr export adr/accepted --format json | \
  jq '.[] | {id, date: .metadata.date, status, projects: .scope.projects}' | \
  jq -s 'sort_by(.date)'

# Generate Markdown table
adr export adr/accepted --format json | \
  jq -r '.[] | "| \(.id) | \(.title) | \(.status) | \(.metadata.date) |"'
```

### Compliance Reporting

Generate compliance reports:

```bash
# LGPD-tagged decisions
adr export adr --format json --filter-status accepted | \
  jq '[.[] | select(.governance.compliance | contains(["LGPD"]))] |
      {count: length, decisions: [.[] | {id, title}]}'

# Critical decisions by quarter
adr export adr --filter-classification critical --format json | \
  jq 'group_by(.metadata.date[0:7]) |
      map({month: .[0].metadata.date[0:7], count: length})'
```

## Best Practices

1. **Use JSONL for pipelines**: Streaming, constant memory
2. **Filter early**: Export only what you need
3. **Version exports**: Tag exports with timestamps
4. **Validate output**: Always pipe to `jq` for validation
5. **Compress for storage**: `gzip` JSONL files (70% reduction)
6. **Monitor hash changes**: Track ADR evolution via `metadata.hash`
7. **Automate exports**: Use git hooks for auto-sync

## Examples Gallery

### Daily Knowledge Sync

```bash
#!/bin/bash
# Sync accepted ADRs to CEREBRO daily

DATE=$(date +%Y-%m-%d)
adr export adr/accepted \
  --format jsonl \
  --filter-status accepted \
  --compact > /tmp/adr_${DATE}.jsonl

# Upload to CEREBRO
cerebro-cli sync /tmp/adr_${DATE}.jsonl

# Cleanup old exports (keep 7 days)
find /tmp -name 'adr_*.jsonl' -mtime +7 -delete
```

### Project Documentation

```bash
# Generate project-specific docs
for project in CEREBRO PHANTOM SPECTRE NEUTRON; do
  adr export adr/accepted \
    --filter-project $project \
    --filter-status accepted \
    --format json > docs/${project}/decisions.json
done
```

### Architecture Review

```bash
# Export critical decisions for review
adr export adr \
  --filter-classification critical \
  --since 2026-01-01 \
  --format json | \
  jq '.[] | {id, title, date: .metadata.date, projects: .scope.projects}' > review.json
```

---

For more examples, see the [README](../README.md) or run `adr export --help`.
