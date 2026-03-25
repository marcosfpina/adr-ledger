# Science Paper Checklist

> Use this checklist to verify your paper is complete before submission.
> Check off items as you complete them.

---

## Pre-Writing

- [ ] Identify target venue (conference: SOSP, OSDI, EuroSys, NSDI / journal: IEEE/ACM)
- [ ] Read venue submission guidelines (word count, format, blind review requirements)
- [ ] Review 5-10 recent papers from target venue (understand expected style/depth)
- [ ] Define research questions clearly
- [ ] Collect all experimental data and metrics

---

## Abstract (~200-250 words)

- [ ] Background/Context (1-2 sentences)
- [ ] Problem statement (1-2 sentences)
- [ ] Approach/Solution (2-3 sentences)
- [ ] Key results (2-3 sentences with numbers)
- [ ] Conclusion/Implications (1 sentence)
- [ ] Keywords (5-8 relevant terms)
- [ ] **Verification**: Does abstract answer "Why should I read this paper?"

---

## 1. Introduction (~2-3 pages)

### 1.1 Motivation
- [ ] Establishes importance of problem domain
- [ ] Provides concrete examples/scenarios
- [ ] Explains why existing solutions insufficient

### 1.2 Problem Statement
- [ ] Clearly defines research problem
- [ ] Lists specific research questions (3-5)
- [ ] Explains scope and boundaries

### 1.3 Contributions
- [ ] Lists 5-7 concrete contributions
- [ ] Each contribution is measurable/verifiable
- [ ] Avoids vague claims ("we improve performance")
- [ ] Uses active voice ("We demonstrate X", not "X is demonstrated")

### 1.4 Organization
- [ ] Roadmap of remaining sections
- [ ] Helps reader navigate paper

---

## 2. Related Work (~2-4 pages)

### Coverage
- [ ] Architectural governance (ADRs, knowledge management)
- [ ] Event-driven architecture (message brokers, microservices)
- [ ] ML infrastructure (workflow orchestration, distributed training)
- [ ] Local-first systems (local AI, edge computing)
- [ ] Declarative infrastructure (NixOS, IaC)

### For Each Related Work Category
- [ ] Cites 3-5 relevant papers
- [ ] Summarizes each work fairly (1-2 sentences)
- [ ] Identifies gap or limitation
- [ ] Explains how your work differs/improves
- [ ] **Avoids**: Strawman arguments, dismissive tone

### Integration
- [ ] Organized thematically (not chronologically)
- [ ] Builds narrative leading to your contributions
- [ ] Cross-references to your work (Section 3.X addresses gap Y)

---

## 3. Architecture/Design (~3-5 pages)

### 3.1 Design Principles
- [ ] Lists 5-7 core principles
- [ ] Each principle explained with rationale
- [ ] Principles guide architectural choices

### 3.2 System Overview
- [ ] High-level architecture diagram (clear, labeled)
- [ ] Explains layered structure
- [ ] Identifies major components

### 3.3 Component Descriptions
- [ ] ADR-Ledger (governance layer)
  - [ ] Architecture
  - [ ] Key algorithms (AST parsing, knowledge extraction)
  - [ ] Integration points
- [ ] NEUTRON (infrastructure layer)
  - [ ] NixOS modules (security, networking, compute)
  - [ ] Temporal + Ray + MLflow stack
  - [ ] ADR compliance enforcement
- [ ] SPECTRE (communication layer)
  - [ ] Event types (30+ defined)
  - [ ] NATS patterns (pub/sub, request-reply, queue groups)
  - [ ] Observability (TimescaleDB, Neo4j)
- [ ] PHANTOM (document intelligence)
  - [ ] CORTEX engine (chunking, classification, embedding)
  - [ ] Local LLM (llama.cpp integration)
  - [ ] Hybrid cloud fallback
- [ ] CEREBRO (knowledge extraction)
  - [ ] GCP Vertex AI integration
  - [ ] Credit validation (BigQuery audit)
  - [ ] RAG pipeline

### 3.4 Interactions
- [ ] Sequence diagrams for key workflows
- [ ] Data flow diagrams
- [ ] Explains how components communicate (events, APIs)

---

## 4. Implementation (~2-4 pages)

### Technology Stack
- [ ] Table summarizing tech stack per component
- [ ] Justification for key technology choices

### Code Metrics
- [ ] Lines of code (total, per component)
- [ ] Languages used (Rust, Python, Nix, etc.)
- [ ] Dependencies (count, vetted for security)

### Implementation Highlights
- [ ] 2-3 code snippets (key algorithms, not trivial getters/setters)
- [ ] Pseudocode for complex logic
- [ ] Explains non-obvious design decisions

### Challenges & Solutions
- [ ] Identifies 2-3 implementation challenges
- [ ] Describes solutions
- [ ] Lessons learned

---

## 5. Evaluation (~4-6 pages)

### 5.1 Experimental Setup
- [ ] Hardware specifications
- [ ] Software versions
- [ ] Datasets (size, characteristics, source)
- [ ] **Reproducibility**: Enough detail for others to replicate

### 5.2 Use Cases / Experiments
- [ ] 4-6 distinct experiments
- [ ] Each experiment has:
  - [ ] Clear objective
  - [ ] Setup description
  - [ ] Metrics measured
  - [ ] Results table or chart
  - [ ] Analysis (why these results?)

### Specific Experiments
- [ ] **Use Case 1**: ADR workflow (decision propagation time)
- [ ] **Use Case 2**: Repository analysis (cost, latency: local vs cloud)
- [ ] **Use Case 3**: ML pipeline (adaptive vs fixed strategies)
- [ ] **Use Case 4**: Event-driven monitoring (self-healing time)
- [ ] **Ablation Study**: Disable components, measure impact
- [ ] **Fault Tolerance**: Simulate crashes, measure recovery

### Metrics
- [ ] Performance (latency, throughput)
- [ ] Cost (absolute $, % savings vs baselines)
- [ ] Quality (accuracy, MMLU scores)
- [ ] Reliability (MTTR, uptime %)
- [ ] Scalability (how system behaves with 10×, 100× load)

### Comparison Baselines
- [ ] Cloud-only approaches (OpenAI, AWS SageMaker, etc.)
- [ ] Traditional orchestration (Airflow, Kubeflow)
- [ ] Monolithic architectures

### Visualizations
- [ ] 6-10 figures total
- [ ] Bar charts (comparisons)
- [ ] Line charts (trends over time)
- [ ] Architecture diagrams
- [ ] All figures have:
  - [ ] Clear labels
  - [ ] Legend
  - [ ] Caption explaining what's shown
  - [ ] Referenced in text ("Figure 3 shows...")

---

## 6. Discussion (~2-3 pages)

### 6.1 Key Findings
- [ ] Summarizes main results (bullet points)
- [ ] Highlights surprising or unexpected findings
- [ ] Connects to research questions (answers each one)

### 6.2 Limitations
- [ ] Honestly discusses weaknesses (reviewers will find them anyway)
- [ ] Explains mitigation strategies
- [ ] Scopes where approach doesn't apply

### 6.3 Generalizability
- [ ] Who can benefit from this work?
- [ ] What types of organizations/problems?
- [ ] When is this approach NOT suitable?

### 6.4 Threats to Validity
- [ ] Internal validity (experimental design flaws)
- [ ] External validity (generalization to other contexts)
- [ ] Construct validity (are we measuring the right thing?)
- [ ] For each threat: acknowledge + mitigation

---

## 7. Conclusion (~1 page)

- [ ] Restates problem briefly
- [ ] Summarizes approach (high-level)
- [ ] Lists key contributions (concise)
- [ ] States quantitative results (cost savings, speedup, etc.)
- [ ] **Future Work**: 5-7 concrete directions
  - [ ] Each is specific (not "improve performance")
  - [ ] Explains why direction is valuable
- [ ] **Impact Statement**: Broader implications

---

## 8. References

- [ ] 30-50 references (typical for systems/ML papers)
- [ ] Mix of classic papers (foundational) and recent work (state-of-art)
- [ ] Proper citation format (IEEE, ACM, or venue-specific)
- [ ] All citations have complete info (authors, title, venue, year, DOI/URL)
- [ ] No broken links
- [ ] **Verification**: Every claim in paper is either:
  - [ ] Your original work (evaluated in Section 5)
  - [ ] Cited to external source

---

## Formatting

- [ ] Follows venue template (LaTeX class, Word template)
- [ ] Page limit respected (including references, appendices)
- [ ] Font size, margins correct
- [ ] Figures high-resolution (300+ DPI for raster images)
- [ ] Tables properly formatted (LaTeX booktabs or equivalent)
- [ ] Consistent terminology (don't switch between "workflow" and "pipeline")
- [ ] No orphan/widow lines (single line at top/bottom of page)

---

## Writing Quality

- [ ] Proofread for typos, grammar errors
- [ ] Active voice preferred ("We implement X" vs "X is implemented")
- [ ] Technical jargon defined on first use
- [ ] Acronyms defined (ADR = Architecture Decision Record)
- [ ] Consistent tense (past for experiments: "We measured...", present for system: "PHANTOM uses...")
- [ ] Paragraphs flow logically (topic sentence → supporting sentences → transition)
- [ ] No walls of text (break up paragraphs, use bullet points where appropriate)

---

## Pre-Submission Review

### Self-Review
- [ ] Read paper start-to-finish as if you're a reviewer
- [ ] Does introduction hook you? (if not, rewrite)
- [ ] Can you understand system without reading code? (if not, improve Section 3)
- [ ] Are results convincing? (if not, add experiments or improve analysis)
- [ ] Are limitations honestly discussed? (reviewers respect honesty)

### Peer Review (Internal)
- [ ] Share with 2-3 colleagues
- [ ] Ask specific questions:
  - [ ] What's unclear?
  - [ ] What's unconvincing?
  - [ ] What's missing?
- [ ] Incorporate feedback

### Final Checks
- [ ] Spell check (LaTeX: `aspell -t check paper.tex`)
- [ ] Compilation (LaTeX compiles without errors/warnings)
- [ ] References formatted correctly (BibTeX style)
- [ ] Figures render correctly in PDF
- [ ] Paper meets all venue requirements (checklist, formatting)
- [ ] Supplementary materials prepared (if applicable: code, datasets, appendices)

---

## Submission

- [ ] Submission system account created
- [ ] Abstract submitted (if required before full paper)
- [ ] PDF uploaded
- [ ] Supplementary materials uploaded
- [ ] Copyright form signed (if required)
- [ ] Conflict of interest declared
- [ ] Confirmation email received
- [ ] **Backup**: Keep local copy, submitted version in version control

---

## Post-Submission

- [ ] Track submission status
- [ ] Prepare for reviews (expect 6-12 weeks)
- [ ] If rejected: 
  - [ ] Read reviews carefully (multiple times)
  - [ ] Identify valid criticisms
  - [ ] Revise and resubmit to different venue
- [ ] If accepted:
  - [ ] Prepare camera-ready version
  - [ ] Prepare presentation (conference talk or poster)
  - [ ] Plan for artifact evaluation (if offered)

---

## Target Venues (Suggested)

### Systems Conferences (Tier 1)
- **SOSP** (ACM Symposium on Operating Systems Principles) - Biennial, Oct
- **OSDI** (USENIX Symposium on Operating Systems Design and Implementation) - Biennial, Jul
- **EuroSys** (European Conference on Computer Systems) - Annual, Apr
- **NSDI** (USENIX Symposium on Networked Systems Design and Implementation) - Annual, Apr

### ML/AI Conferences (Tier 1-2)
- **MLSys** (Conference on Machine Learning and Systems) - Annual, Jun
- **SoCC** (ACM Symposium on Cloud Computing) - Annual, Nov
- **ICSE** (International Conference on Software Engineering) - Annual, May

### Journals
- **ACM Transactions on Computer Systems (TOCS)**
- **IEEE Transactions on Software Engineering (TSE)**
- **Journal of Systems and Software (JSS)**

---

**Estimated Timeline**:
- Draft writing: 4-6 weeks
- Internal review: 1 week
- Revisions: 2 weeks
- Submission: 1 day
- Review period: 6-12 weeks
- **Total**: ~4-6 months from start to decision
