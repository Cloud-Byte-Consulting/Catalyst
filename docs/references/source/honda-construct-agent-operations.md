# Honda Construct — Japanese Manufacturing Principles Applied to AI Agent Operations

A comprehensive synthesis of the Toyota Production System (TPS) and Honda's manufacturing philosophy as a coherent operating model for AI coding agents. Each principle is mapped to the substantive technical patterns from the unattended-agent architecture, the AI-agents engineering literature, the agent-orchestration cookbook, dimensional modeling rigour, and platform-engineering practice.

> **Why "Honda Construct"?** The relay codebase uses this phrase as the local vocabulary for its TPS-inspired engine rules (`internal/construct/muda.go` strips conversational filler as Over-production waste; `feat(construct): enforce Honda-inspired agentic principles in relay engine` is on the main branch). This document expands the local vocabulary into a full operating philosophy, organising the technical material across the four source domains under a single coherent frame.

---

## Table of contents

- [Why this synthesis exists](#why-this-synthesis-exists)
- [The factory-floor mental model](#the-factory-floor-mental-model)
- [How to read this document](#how-to-read-this-document)
- **Part I — TPS principles, fully expanded**
  - [Jidoka — autonomation, the cord that stops the line](#jidoka--autonomation-the-cord-that-stops-the-line)
  - [Andon — visible signals that route to whoever can fix it](#andon--visible-signals-that-route-to-whoever-can-fix-it)
  - [JIT and Pull — only what's needed, only when it's needed](#jit-and-pull--only-whats-needed-only-when-its-needed)
  - [Heijunka — level the workload](#heijunka--level-the-workload)
  - [Kaizen — small continuous improvement, with measurement](#kaizen--small-continuous-improvement-with-measurement)
  - [Poka-yoke — mistake-proofing as mechanical guarantee](#poka-yoke--mistake-proofing-as-mechanical-guarantee)
  - [Muda, Mura, Muri — three families of waste](#muda-mura-muri--three-families-of-waste)
  - [5S — workspace discipline as a precondition to good work](#5s--workspace-discipline-as-a-precondition-to-good-work)
  - [Standardised work](#standardised-work)
  - [SMED — rapid changeover](#smed--rapid-changeover)
  - [Genchi Genbutsu — go and see for yourself](#genchi-genbutsu--go-and-see-for-yourself)
  - [Hansei — honest reflection](#hansei--honest-reflection)
- **Part II — Honda-specific contributions**
  - [The Three Joys](#the-three-joys)
  - [Sangen Shugi — the three reals](#sangen-shugi--the-three-reals)
  - [Wai-Gaya — flat-hierarchy structured argument](#wai-gaya--flat-hierarchy-structured-argument)
- **Part III — The composite operating model**
  - [Layer mapping — principles × architectural layers](#layer-mapping--principles--architectural-layers)
  - [The complete artifact stack](#the-complete-artifact-stack)
  - [The lifecycle of one agent slice — annotated](#the-lifecycle-of-one-agent-slice--annotated)
- **Part IV — Agent engineering practices, mapped**
  - [Cognitive architecture choices](#cognitive-architecture-choices)
  - [Memory hierarchies](#memory-hierarchies)
  - [Tool-use and function-calling](#tool-use-and-function-calling)
  - [Multi-agent coordination](#multi-agent-coordination)
  - [Confidence calibration and refusal](#confidence-calibration-and-refusal)
  - [Domain-specific agent architectures](#domain-specific-agent-architectures)
  - [Embodied agents — what physical-system constraints teach digital ones](#embodied-agents--what-physical-system-constraints-teach-digital-ones)
- **Part V — Agent orchestration patterns**
  - [Five cookbook patterns, smallest to largest](#five-cookbook-patterns-smallest-to-largest)
  - [The DAG runner — Heijunka of compute](#the-dag-runner--heijunka-of-compute)
  - [Live-canvas hot-reload — Andon as a UI surface](#live-canvas-hot-reload--andon-as-a-ui-surface)
- **Part VI — Data modeling for agent operations**
  - [Why dimensional rigour matters for agent state](#why-dimensional-rigour-matters-for-agent-state)
  - [Grain — the most consequential decision](#grain--the-most-consequential-decision)
  - [Conformed dimensions — shared vocabulary across tools](#conformed-dimensions--shared-vocabulary-across-tools)
  - [Slowly-changing dimensions for agent state history](#slowly-changing-dimensions-for-agent-state-history)
  - [Fact-table patterns for agent telemetry](#fact-table-patterns-for-agent-telemetry)
  - [Data Vault when you're operating a fleet](#data-vault-when-youre-operating-a-fleet)
  - [Streams + tasks + dynamic tables — real-time agent telemetry](#streams--tasks--dynamic-tables--real-time-agent-telemetry)
- **Part VII — Platform engineering for agent fleets**
  - [Internal Developer Platform (IDP) for agent operators](#internal-developer-platform-idp-for-agent-operators)
  - [Golden paths](#golden-paths)
  - [GitOps for agent configuration](#gitops-for-agent-configuration)
  - [SRE-style error budgets](#sre-style-error-budgets)
  - [Kubernetes-style runtime constraints](#kubernetes-style-runtime-constraints)
  - [Observability for agent fleets](#observability-for-agent-fleets)
  - [Identity-native infrastructure access for agents](#identity-native-infrastructure-access-for-agents)
- **Part VIII — Anti-patterns: cargo-cult Lean**
- **Part IX — Adoption playbook**
- **Part X — Reference implementation in the local codebases**
- [Glossary](#glossary)
- [References to the source corpus](#references-to-the-source-corpus)

---

## Why this synthesis exists

Manufacturing and AI-agent operations face the same core problem: **how do you produce a stream of correct outputs, reliably, at scale, without a human in every loop?** Toyota and Honda solved this for physical goods over fifty years. The principles they evolved transfer almost without translation to autonomous coding agents — what changes is the unit of production (a pull request instead of a car door) and the medium (LLM tokens and tool calls instead of sheet metal).

The unattended-agent architecture documented in this corpus — 173 PRs in 53 hours, mostly without the developer at the desk — is a Toyota factory floor in miniature. Marker files are the andon system. The harness lock is poka-yoke. The exec plan is standardised work. The agent's `blocked` exit is the cord that stops the line. The CI gates are jidoka.

The AI-agents literature supplies the *what the agent can be*: cognitive architectures, ReAct, tool use, memory hierarchies, multi-agent debate, refusal patterns. The agent-orchestration cookbook supplies the *how to fan out work*: headless agents, DAG decomposition, rank-parallel dispatch, live-canvas hot-reload. Data modeling supplies the *how to structure the durable state* the agent reads from and writes back to: grain declarations, conformed dimensions, slowly-changing dimensions for state history, fact tables for telemetry. Platform engineering supplies the *how to operate a fleet of agents reliably*: IDPs, golden paths, error budgets, observability, identity-native access.

Honda Construct is the philosophy that ties all of those into a coherent system. None of the source domains by itself is sufficient; combined under the TPS frame they describe a complete operating model.

The argument of this document, in one sentence:

> **Treat your AI agent operation as a Toyota assembly line, not as a smarter programmer.**

Everything else is implementation of that one stance.

---

## The factory-floor mental model

Picture a Toyota assembly line. A car body moves down the line. At each station, a worker — or a robot — does one bounded operation: install the door, wire the dash, tighten the bolts on the suspension. Each station has:

- A **standardised work instruction** at hand, defining the best-known method.
- A **takt time** — the rhythm at which work must complete to match downstream pull.
- A **proving check** that confirms the operation was done right before the body moves on.
- An **andon cord**: pull it, the line stops, the team converges, the defect is fixed at source.
- A **capability boundary**: the worker has the tools and parts for this station, no more.

Now picture the unattended agent loop. The "car body" is an issue moving through `ready-for-agent` → `agent-working` → `done` (or `blocked-on-human` and back). At each station, the agent does one bounded operation: ship one thin slice (red → green → refactor). Each station has:

- A **standardised exec plan** in the issue body — milestone, next slice, proving test, lint command, expected red, files in scope, validation evidence.
- A **takt time** — the agent timeout (default 30 minutes per session in `relay-worker`); slices are sized to fit.
- A **proving CI run** — branch protection requires green before merge.
- A **marker file / label**: `blocked-on-human` is the andon cord; the worker's next tick skips this item until a human resolves.
- A **capability boundary**: the agent's tool surface (relay's `internal/tools/`) bounds what it can touch.

Same shape. Different unit. Same philosophy works.

The mistake people make when running agents is treating them as **stochastic programmers** rather than as **disciplined factory operators**. The architecture in the rest of this document is what disciplines them.

---

## How to read this document

The document is structured as a reference, not an essay. Each Japanese principle gets a section organised the same way:

1. **Definition** — what the principle means in the original manufacturing context.
2. **What this looks like in agent operations** — the artifacts and patterns from the source corpus that implement the principle.
3. **Concrete examples** — code shapes, decision tables, configurations from the actual repositories and source documents.
4. **Cross-references** — pointers to the AI-agents, agent-orchestration, data-modeling, platform-engineering source material that goes deeper.
5. **Anti-patterns** — common ways of getting it wrong.

Read linearly for the philosophy, or skip to the principle you're trying to apply. Parts III–VII expand the cross-domain material that appears throughout Parts I–II; if you want the full agent-engineering content (ReAct, memory, tool-use, multi-agent), Part IV is your jump-in point. Part V is the orchestration cookbook. Part VI is data modeling for agent state. Part VII is platform engineering for agent fleets. Part VIII is the anti-patterns. Part IX is a step-by-step adoption guide. Part X catalogues which artifacts in the local codebases implement which principles.

---

# Part I — TPS principles, fully expanded

## Jidoka — autonomation, the cord that stops the line

> *"Autonomation, with a human touch." Build quality in by giving every machine the authority — and the obligation — to halt the line when it detects a defect.*

### What this looks like in agent operations

The principle: every layer must have an automated stop condition. If a human is the only thing that catches the defect, the human is in the loop.

Three places jidoka is implemented in the unattended-agent architecture:

1. **The agent has the authority to write `blocked-on-human`** the moment it hits a precondition it cannot resolve — expired token, ambiguous spec, failing CI on its own slice. It does not silently retry, does not drift to other work, does not "try to fix the token itself." The relay-worker `processItem` flow records this explicitly: when `dispatchAgent` returns `OutcomeBlocked`, the WorkSource's `Block(ctx, id, reason)` is called, which applies the marker label and posts the reason as an audit comment.
2. **The CI gates have the authority — and obligation — to reject** any PR the agent opens that fails tests, modifies the harness, or lacks an exec-plan reference. Branch protection is the line stop; auto-merge is the line resume — both gated by the green build.
3. **The relay `MudaStripper`** (`internal/construct/muda.go`) is jidoka applied to the *output stream*: detect filler tokens at emission time (`"Certainly!"`, `"I can help with that."`, `"Sure thing!"`), strip them before they escape into the user's context. The "machine" stops the defect at source, the moment of generation, not after it has propagated.

### Concrete patterns from the source corpus

**Refusal as Jidoka in the AI-agents literature** — strong refusal patterns from the Ethics and Domain-Specific sections (`ai-agents.md`):

- The agent refuses out-of-scope verbs (`verb_not_allowed` in the work-graph control plane).
- The agent refuses to bypass policy (the Compliance-Driven Code Agent's pre-commit gate; OPA/Rego policies that mark a query `deny` when PAN data appears unencrypted).
- The agent refuses to act without verification (the Ethical Reasoning Agent's `evaluate_action` runs every proposed action through five compliance checkers — human rights, well-being, accountability, transparency, awareness of misuse — and only returns the action if all pass; otherwise it generates a mitigation).

**Confidence-thresholded refusal** — the Customer Service Autonomous Agent design from `ai-agents.md` calls `escalate_to_human` whenever the confidence score for an intent classification falls below the configured threshold:

```python
def process_request(self, user_message, session_context) -> Response:
    intent     = self.intent_classifier.classify(user_message)
    sentiment  = self.sentiment_analyzer.analyze(user_message)
    policy     = self.policy_store.lookup(intent)
    confidence = self.confidence_model.score(intent, sentiment, session_context)
    if confidence < self.escalation_threshold:
        return self.escalate_to_human(session_context, reason="low_confidence")
    return self.generate_response(policy, session_context)
```

The escalation **is** jidoka. The system does not guess and ship; it stops and surfaces.

**Pre-commit compliance gate** — the same source's Compliance-Driven Code Agent enforces policies like PCI-DSS or HIPAA at the merge boundary. The agent generates code, the SAST + OPA layer scans it, and either the agent gets a remediation prompt or the merge is blocked. This is jidoka extended into a regulatory dimension: the line stops not just on functional defects but on policy violations.

### Anti-patterns

- **Soft refusals** — the agent says "I'll try anyway" or "let me work around this." That isn't jidoka; that's the line continuing past a defect.
- **Retry storms** — the agent hits the same auth error five times before stopping. The first failure is the andon signal; subsequent retries are noise that wastes quota and obscures the actual cause. `relay-worker`'s `pingAgent` health check exists for this reason: surface the connectivity issue before treating it as an agent-runtime failure.
- **Silent comment-outs** — the agent's "fix" for a failing test is to comment out the assertion. Without the harness lock, this passes CI; with the harness lock, the diff to the test file fails the gate and the agent must produce real fix.

---

## Andon — visible signals that route to whoever can fix it

> *"The visible signal of trouble." Make problems immediately apparent to whoever can fix them.*

### The four forms andon takes in agent operations

| Andon mechanism | Audience | Latency target | Source artifact |
|---|---|---|---|
| **Marker files / labels** | The supervising loop | Per-tick (≤ 5 min) | `blocked-on-human` label on the issue, applied by `relay-worker.WorkSource.Block` |
| **Issue / ticket comments** | The human reviewer | Whenever they read the issue | Posted by the agent via `relay-worker.WorkSource.Comment` |
| **Structured logs** | The operator | Real-time stream | `journalctl -u relay-worker` (systemd-supervised); `slog` JSON for fleet aggregation |
| **PR status checks** | Reviewers + the agent itself | At PR-open time | GitHub / GitLab status checks tied to the CI workflow |

### What "routes to the right audience" actually requires

The cardinal rule: **andon must surface to the right audience automatically**. A failure that requires the developer to remember to check the dashboard is not andon — it is hope.

For agent operations, that means:

1. **Marker labels page the supervising loop, not a human.** When the agent writes `blocked-on-human`, the worker on the next tick *automatically skips* the item. The human gets paged via the comment, where the reason is documented. They are not pulled in until they're needed.
2. **Comments tag a human.** The block reason posted by `relay-worker` should `@mention` the issue assignee or the PR review-team alias. A `blocked-on-human` label without a notification is a label nobody sees.
3. **Logs are streamable.** The `journalctl` output survives the SSH disconnect. When the developer comes back the next morning, the full transcript of every tick is there. They don't reconstruct from the agent's memory; they read the genbutsu.
4. **PR status checks are gates.** Reviewers don't need to run the test suite locally — the CI run already did, and the result is on the PR. Andon for code quality is the red status badge.

### Andon at the fleet scale

When you're operating more than one agent, the dashboard becomes the andon system. The `ai-agents.md` "Agent Deployment and Operations" section recommends — and the relay codebase implements via `slog` — structured logs at every layer: agent emits, worker emits, dispatcher emits, all correlated by a trace id. The fleet observability minimum:

- **Metrics**: `agent_session_duration_seconds` (histogram), `marker_transition_total{from,to}` (counter), `tool_call_total{tool}` (counter), `model_token_usage_total{tier=low|med|high}` (counter), `blocked_on_human_duration_seconds` (histogram).
- **Traces**: one trace per agent session, with spans for each tool call, each sub-LM dispatch, each PR operation.
- **Profiles**: continuous profiling (Pyroscope or equivalent) catches the case where an agent is wedged on a regex backtrack rather than actually doing work.

The pattern transfers from SRE practice in the `devops-and-platform-engineering.md` corpus: USE (utilization, saturation, errors) and RED (rate, errors, duration) metrics applied to the agent endpoint, not just the application stack.

### Live-canvas hot-reload — andon as a UI surface

The agent-orchestration cookbook's DAG runner writes a `.canvas.tsx` file that the IDE hot-recompiles on every state transition. The user sees `PENDING → RUNNING → FINISHED/ERROR` transitions live, plus token-by-token streaming inside each task card. This is andon as UX:

| Surface | What re-renders on write |
|---|---|
| `.canvas.tsx` (Cursor) | The canvas pane in the IDE |
| Mermaid `.md` (any IDE) | The markdown preview pane |
| HTML + `vite --watch` | The browser tab |
| `.svg` in any IDE | The SVG preview |
| `~/.rlm_state/run.json` | A `watch -n 1 jq …` in a side terminal renders a live status table |

The contract the runner needs from the surface is just "write a file, render gets re-run." Pick whichever your toolchain supports. The principle is the same whether the substrate is a TPS andon board, a Cursor canvas, or a tail-watched JSON file: state changes are visible, immediately, to whoever can act on them.

### Anti-patterns

- **Slack channel nobody is paged on.** A `#agent-blocked` Slack channel that nobody is paged on is not andon. Andon **routes to the actor who can fix it**, with a latency low enough that the line doesn't sit idle. If your agent can sit blocked overnight, your andon is broken.
- **Logs without correlation IDs.** When a fleet of agents share one log stream and you can't grep by session, the andon is structurally compromised — you see that something failed, not which session, which issue, or which tool call.
- **Status checks that don't gate.** A green/red status check that doesn't actually block merge is decoration. Branch protection is what makes it andon.

---

## JIT and Pull — only what's needed, only when it's needed

> *"Just in time. Pull the next unit of work only when capacity is ready for it."*

### Pull-based work in the unattended loop

Three layers of pull in the agent operating model:

1. **The worker pulls from the queue.** `relay-worker` does not push slices into the agent at a fixed rate. It pulls from the `ready-for-agent` queue when its previous tick has finished. If the queue is empty, the timer fires and the worker exits cleanly with `ErrNoReadyItems`. The cron schedule (`@every 5m`) is the takt rate; the marker labels gate whether anything actually happens.
2. **The agent pulls the next slice.** The agent does not plan ten slices ahead. It pulls the next item from the exec plan when the previous one merges. The exec plan template — milestone, next slice, proving test, files in scope — names exactly one slice at a time. Future slices are listed but not staged.
3. **The orchestrator pulls sub-LLM dispatches.** The RLM root LM does not dispatch sub-LLM calls speculatively — only when it determines a chunk needs reading. The complexity-tier system (`rlm-subcall-low/med/high`) lets the root pull the right model for each chunk, not the highest-cost model "just in case."

### JIT for context windows

The RLM principle that "you only feed the model the chunk it needs, exactly when it needs it" is the same idea applied to tokens. The model's context window is the work-in-process buffer; you keep it lean by pulling only what the current step requires.

The agent-orchestration cookbook's DAG runner takes this further: each rank's tasks are pulled into execution **only when their dependencies have completed**. Independent tasks fan out via `Promise.all`; dependent ones wait. The runner never has a backlog of "I'll do this later" — it does the work that is ready, then exits.

### The "chunking strategies" decision table

JIT for context manifests in the chunking strategy. From `ai-agents.md`:

| Strategy | Chunk Size | Best For |
|---|---|---|
| Fixed-size | 256–512 tokens | Uniform documents |
| Sentence | Variable | Conversational text |
| Semantic | Variable | Dense technical prose |
| Hierarchical | Multi-level | Long structured documents |
| Sliding window | Overlap 20% | Avoid boundary artifacts |

The gotcha called out in the source: chunk size is the most impactful hyperparameter. Too small → loss of context; too large → diluted embeddings. JIT is the lens — pull the smallest chunk that contains the answer, no more.

### The Heijunka × JIT interaction

Pure JIT without leveling produces mura (unevenness). If the queue suddenly fills with twenty `ready-for-agent` items, a worker pulling JIT-style would attempt all twenty back-to-back and saturate downstream capacity. `relay-worker`'s `MaxItemsPerTick` cap (default 1) is the bridge: pull, but only one at a time. Heijunka shapes the pull cadence so JIT doesn't degenerate into bursts.

### Anti-patterns

- **Push-shaped queues**. If a system enqueues all open issues into the agent's input queue at once, you don't have JIT — you have a stockroom that the agent must drain.
- **Speculative pre-fetch.** Reading "the chunks you might need next" into context is over-production muda. Only pull when needed.
- **Hidden backlogs.** A `ready-for-agent` queue that grows unbounded because no agent is consuming it means the pull signal isn't propagating. Add an alert.

---

## Heijunka — level the workload

> *"Level the workload. Smooth out the peaks and valleys so quality stays consistent."*

### Practical levelling in agent ops

Three levers:

1. **Thin-slice exec plans.** Force every PR to be roughly the same size. The exec plan template — one slice per session — eliminates "huge refactor PR followed by ten typo PRs." The agent's takt time stays consistent, which means the human review cadence stays predictable.
2. **`MaxItemsPerTick = 1`.** In `relay-worker`, this prevents a tick from dumping ten PRs at once when the queue is full. Spread the work over ticks; reviewers and CI capacity get a steady stream rather than a burst.
3. **Complexity tiers.** The `HIGH/MED/LOW` model mapping (in both the rlm-context-agent's `rlm-subcall-{low,med,high}` agents and the agent-orchestration cookbook's DAG runner) levels *cost*. Heavy reasoning gets routed to opus, mechanical lookups to haiku. The token budget per session stays predictable.

### The complexity-to-model decision table

From the agent-orchestration cookbook:

| Complexity | Model | When to use |
|---|---|---|
| `HIGH` | claude-opus-4-7 / gpt-5.3-codex | Novel reasoning, tricky design tradeoffs, hard refactors |
| `MED` | claude-sonnet-4-6 / composer-2 | Typical implementation work |
| `LOW` | claude-haiku-4-5 / auto-low | Mechanical tasks, lookups, format conversions |

Override any subset inline in the DAG via top-level `models`, or ship a reusable profile JSON. Precedence: defaults < DAG `models` < `--models-file`. The principle: each unit of work is sized to its station.

### Heijunka of compute via rank parallelism

The DAG runner's whole point is rank-level parallelism via `Promise.all`. A linear A→B→C→D DAG wastes that capability. The cookbook's quality bar:

> When you sketch the rank structure, at least one rank should contain more than one task in any non-trivial problem. If your DAG is a single chain of one-task ranks, you almost certainly missed parallelism — go back and look again.

Five rules from the source for maximising parallelism:

1. **Default to no dependencies.** Add `depends_on` only when the child literally cannot start without the parent's output. "Logically follows" is not a dependency.
2. **Split read-only research and discovery into a wide first rank.** Codebase greps, doc reading, dependency scans, schema lookups, test inventory — these almost always share rank 1 with no edges.
3. **Fan out post-implementation work.** Tests, docs, changelog entries, type updates, lint fixes typically depend only on the same implementation task — put them in one rank, not a chain.
4. **Use diamonds, not lines.** If two tasks both feed a third, model that explicitly: rank 1 has the two parents, rank 2 is the merge.
5. **Same-rank file-write safety.** The one hard constraint: don't put two tasks in the same rank if they would write the same file. Either serialize them with a `depends_on`, or merge them.

This is heijunka applied to compute: spread the work across parallel siblings so the wall-clock time matches the longest critical path, not the sum of the chain.

### Heijunka in the throttling layer

The DAG runner's debounce and stream-publish settings shape the load on the IDE / canvas surface:

- **`--debounce 200` ms** — coalesce updates faster than that.
- **`--stream-publish-ms 500` ms** — only republish a task's streaming text snapshot every 500 ms.
- **`STREAM_CAP = 4000` chars per task** — keep the canvas file modest.
- **Cap upstream context passed to children at 2000 chars per parent** — children see *summaries* of upstream output, not the whole transcript.

Each of these is a heijunka knob. They prevent the bursty token stream from overwhelming the downstream consumer.

### Anti-patterns

- **No rate limits on the worker.** A worker with `MaxItemsPerTick = unlimited` will drain the queue in a single tick and overload reviewers and CI. Heijunka requires the cap.
- **Same-tier-for-everything.** If every sub-call uses opus, you've eliminated the cost lever. Tiers exist so the cheap work is cheap.
- **Linear DAGs.** A four-task DAG that is `A → B → C → D` is the same wall time as four sequential agents. The DAG abstraction was wasted.

---

## Kaizen — small continuous improvement, with measurement

> *"Small, continuous improvement is more valuable than big-bang change."*

### Where kaizen lives in the agent operating model

Three loci:

1. **Each thin slice is a kaizen step.** One small change, tested, merged, then the next. Over 173 PRs this compounds into structural change without any single risky PR. This is the unattended-agent architecture's whole reason for existing.
2. **The eval harness measures over time.** `relay-eval` (the relay binary) and the eval section of `ai-agents.md` describe an MLOps-style measurement loop: collect feedback, aggregate into patterns, generate hypotheses, A/B test in shadow mode, promote if metrics improve, rollback if regression detected.
3. **Hansei is the explicit reflection step.** The `/pr-review` skill's per-comment triage; the security-review skill's adversarial pass; the agent's exec-plan update at the end of each session. These turn one slice's lessons into the next slice's standardised work.

### The closed-loop control system from ai-agents.md

The Self-Improving Agent pattern formalises kaizen as a closed-loop:

```
execute → observe → learn → adapt → execute
```

Three feedback signal types:

| Type | Source | Latency |
|---|---|---|
| Explicit | User thumbs up/down, ratings | Immediate |
| Implicit | Task completion, retry rate | Session |
| Synthetic | LLM-as-judge evaluation | Batch |

Hypotheses are typed:

```python
class AdaptationType(str, Enum):
    PROMPT_UPDATE         = "prompt_update"
    THRESHOLD_ADJUSTMENT  = "threshold_adjustment"
    RETRIEVAL_STRATEGY    = "retrieval_strategy"
    TOOL_REORDERING       = "tool_reordering"
```

Each `ImprovementHypothesis` carries a confidence score, evidence count, and a `rollback_safe` flag. The promotion-or-rollback decision is gated on metric movement, not vibe.

The integration with the development lifecycle (per `ai-agents.md`): self-improving agents should be treated as MLOps subjects. Use LangSmith or equivalent observability to track performance metrics across agent versions. The pattern transfers cleanly to Honda Construct: every kaizen step needs a measurement; every measurement needs a baseline; every baseline needs version-tracked evidence.

### Brier score and calibration as kaizen targets

The Confidence-Aware Agent (`ai-agents.md`) provides specific kaizen targets:

- **Brier score** — proper scoring rule for calibration: `BS = (1/N) Σ (p_i - o_i)²`. Lower is better; 0.0 is perfect.
- **Reliability diagrams** — diagnose overconfidence or underconfidence visually.
- **Platt scaling (temperature scaling)** — re-calibrate raw model scores: `p_calibrated = sigmoid((logit(p_raw) - b) / T)`.

A kaizen sprint focused on calibration would: collect a held-out set of agent decisions with ground-truth outcomes, compute the Brier score, train a temperature-scaling layer, validate on a fresh held-out set, deploy the calibrated head, measure the new Brier score. If it dropped, ship; if not, hansei + try again.

### Eval harness as the kaizen substrate

`relay-eval` runs prompt evaluation + UCB-driven prompt optimization. The Upper Confidence Bound (UCB) approach is itself a kaizen-shaped exploration strategy: try prompts that are either currently best (exploit) or insufficiently sampled (explore), with the trade-off mathematically tuned. Every cycle is small, measured, recorded.

### Anti-patterns

- **"We do Kaizen" — but no measurement.** Without an eval harness, no metrics, no facts, then "continuous improvement" is just movement, not progress. Kaizen requires genjitsu (the actual facts).
- **Big-bang refactor PRs.** Tempting in code, lethal under autonomous agents because there is no incremental signal until the giant PR fails. The thin-slice exec plan is the discipline that prevents this.
- **Improvements without rollback.** Every adaptation should carry a `rollback_safe` flag. If you can't roll back, you can't experiment freely; if you can't experiment freely, you can't kaizen.

---

## Poka-yoke — mistake-proofing as mechanical guarantee

> *"Mistake-proofing. Make it impossible — or at least immediately obvious — to do the wrong thing."*

### The poka-yoke devices in the unattended-agent architecture

| Device | What it prevents | Where it lives |
|---|---|---|
| **Harness lock CI** | Agent silently weakening its own correctness signal | `harness-lock.yml` workflow that rejects PRs from non-human authors that touch `tests/conftest.py`, lint configs, workflow files |
| **Branch protection** | Agent merging an unreviewed change to main | Repository settings: required status checks, required review, no force-push |
| **CODEOWNERS** | Agent editing files outside its scope | `.github/CODEOWNERS` requiring named reviewers for sensitive paths |
| **Tool capability surface** | Agent invoking a tool it shouldn't have access to | relay's `internal/tools/` — narrow `Tool` interface; bash, read_file, write_file, math; that's the surface |
| **Math sandbox** | Agent escalating from "evaluate this expression" to "exec a shell" | `internal/tools/math.go` — `expr-lang` Environment map IS the complete capability surface; no fs/network/process access; 10-second default timeout |
| **Marker mutual exclusion** | Two workers picking the same issue | `agent-working` claim via `WorkSource.SetWorking` — atomic-add label (with documented race window for multi-worker setups) |
| **`stop` label** | Agent processing an item the human has explicitly halted | `relay-worker` skips items carrying the `stop` label even if other markers say ready |
| **Tarball sha256 verification** | Tampered knowledge pack landing on disk | rlm-context-agent's `inject` subcommand verifies the manifest's sha256 against the tarball before unpacking |
| **Path-traversal guard** | Malicious tarball escaping the cache directory | `unpack_into_cache` rejects members with absolute paths or `..` parts |
| **`MudaStripper`** | Conversational filler escaping into the user's context | relay's `internal/construct/muda.go` strips known-filler tokens at emission |

### The pattern

Identify every place a defect can originate, install a mechanical check that makes the defect immediately visible (or impossible). Do not rely on "the agent will do the right thing"; rely on "if the agent does the wrong thing, the system catches it before damage."

A poka-yoke is **mechanical**. It must:

- **Reject, not warn.** A warning the agent can ignore is not poka-yoke — it's a checklist.
- **Apply at the boundary.** The check must be at the point where the bad state would persist (CI gate, file write, network call), not somewhere downstream.
- **Be cheap.** Poka-yoke devices that are slow or expensive to apply will be skipped under pressure.

### The Compliance-Driven Code Agent as a poka-yoke layer

The `ai-agents.md` Compliance-Driven Code Agent is poka-yoke for regulatory policy:

- **Semantic code understanding** — beyond pattern matching; interprets what the code does.
- **Static compliance validation** — SAST + OPA/Rego policies.
- **Contextual intervention and remediation** — suggests concrete fixes, not just flags.
- **Audit trail generation** — records every check, finding, and remediation for compliance evidence.
- **Data flow analysis** — traces how PII moves through the codebase.
- **Dynamic policy evolution** — policy rules can be updated without redeploying the agent.

OPA/Rego policy example for PCI-DSS:

```rego
package compliance.pci_dss

deny[msg] {
    input.type == "database_query"
    input.contains_pan == true
    not input.encrypted
    msg := "PAN data must be encrypted at rest per PCI DSS Req 3.4"
}
```

In CI/CD:

```
Developer push → SAST scan → compliance_agent review →
  [if violations] → block merge + generate remediation PR
  [if clean]      → pass to build pipeline
```

This is exactly the harness-lock pattern lifted into the regulatory dimension. Same shape; different defect class.

### The selection funnel as poka-yoke

The `ai-agents.md` Tool-Selection Funnel is a poka-yoke device — at each narrowing step, irrelevant tools are eliminated so the agent literally cannot pick the wrong one:

| Strategy | Mechanism | Best For |
|---|---|---|
| Embedding similarity | Cosine distance on tool descriptions | Large tool registries |
| Intent classification | LLM or fine-tuned classifier | Categorical domains |
| Plan-driven assignment | Planner pre-selects tools | Deterministic workflows |
| Dynamic reranking | Feedback from prior calls | Adaptive agents |

Better than letting the agent see all tools and trusting it to pick well.

### Anti-patterns

- **Poka-yoke as checklist.** A checklist is not mistake-proofing; it's a *reminder*. Poka-yoke is mechanical: the harness lock CI **rejects** the diff, it does not just remind the agent. Branch protection **prevents** the merge. CODEOWNERS **enforces** review. If the device only "alerts" or "warns," it is not poka-yoke and the agent will eventually skip past it.
- **Defenses at the wrong layer.** A linter that runs in the developer's pre-commit hook but not in CI is not poka-yoke for the agent's PRs (the agent doesn't run the developer's hook). The check must be at the branch-protection gate.
- **Soft constraints that fail open.** "If the validator service is down, allow the deploy" turns a poka-yoke into a checkbox. Fail closed unless explicitly waived by a human with the authority to take the risk.

---

## Muda, Mura, Muri — three families of waste

> *"Three families of waste. Eliminate Muda. Smooth out Mura. Avoid Muri."*

| Family | Meaning | In agent ops |
|---|---|---|
| **Muda** (waste) | Activity that consumes resources without adding value | Agent re-reading the same chunk; re-doing work already shipped; conversational filler tokens; commenting on every line of a diff; pulling 50 chunks into context to answer from 3 |
| **Mura** (unevenness) | Inconsistent flow that creates queues or starves capacity | Burst PR queues from no-throttle dispatch; lumpy sub-LLM call patterns; CI runners pegged then idle; review queue overflowing one day, empty the next |
| **Muri** (overburden) | Asking people, machines, or processes to operate beyond their sustainable capacity | 80K-word LLM compositions that hit the watchdog; agents asked to plan ten slices ahead; unlimited tool retries; reviewer expected to read 30 PRs/day |

### Muda — eliminating waste at every layer

Each layer of the agent operating model has its own Muda audit:

**Token Muda.** The relay `MudaStripper` is the prototype. Filler phrases (`Certainly!`, `I can help with that.`, `Sure thing!`), repeated instructions, restating what was just retrieved — all are Muda. The Stripper detects them at emission and either drops them or replaces sensitive paths with `[SENSITIVE PATH REMOVED]`.

**Action Muda.** Tool calls that don't change state. A `read_file` whose output the model already has; a `git status` invoked twice in one session; a `gh issue view` that was already fetched. The orchestrator should cache deterministic reads within the session.

**Comment Muda.** PR review comments that say "LGTM" without evidence. The `/pr-review-triage` skill's discipline — every comment categorised as `fix-now / fix-followup / push-back / clarify-and-resolve / wontfix` with explicit reasoning — eliminates the comment Muda by forcing each comment to do real work.

**Context Muda.** Chunks pulled into context that the synthesis never references. The `extract_per_book.py` Python pipeline is Muda elimination at the corpus level: strip front matter, TOC, back-cover marketing, chapter-end summaries — keep only the load-bearing technical substance. The 93% retention by word count is the measure that the right things were kept and the right things dropped.

**Compute Muda.** The hardcoded `model: haiku` for every sub-call — wasteful when the chunk is a TOC scan, insufficient when the chunk is dense synthesis. The `rlm-subcall-low/med/high` complexity tiers eliminate that Muda.

### Mura — smoothing unevenness

The bursty patterns:

- **Queue burst.** Twenty issues labelled `ready-for-agent` at once. The worker should drain them one per tick, not all at once. `MaxItemsPerTick` enforces this.
- **Sub-LLM dispatch burst.** A 50-chunk full-scan that fires all 50 sub-LLM calls instantly. The cookbook's rank-parallel pattern with bounded concurrency (semaphore around `Promise.all`) smooths this.
- **CI burst.** Ten agent PRs opened in five minutes pegging the runner pool. Tied to the queue burst above; the worker's per-tick cap is the upstream control.

The principle: smooth the load by capping the rate at the *source*, not by adding capacity downstream. Adding more CI runners is muri (overburden — your wallet); slowing the source is mura elimination.

### Muri — avoiding overburden

The book extraction failure mode (LLM agents stalling at 25K-word composition targets) was Muri — overburden. Composing 25K words of internal reasoning before producing any output exceeded the watchdog's 10-minute no-output limit. The fix was not to make the agents tougher; the fix was to take the load off the LLM and give it to deterministic Python (`extract_per_book.py`).

The principle is generic: **when a step in the pipeline keeps failing, look for which actor is being overburdened and offload.**

Other Muri patterns to watch:

- **Reviewer overburden.** If every agent PR needs a reviewer and the agent ships 30 PRs/day, the reviewer is Muri'd. Heijunka caps the rate; auto-merge on green CI offloads the rote review to the gate.
- **Context-window overburden.** Stuffing the entire codebase into one prompt because "it might be relevant" overburdens the model. RLM is the offload — the corpus lives outside the context, the sub-LM reads chunks.
- **Operator overburden.** If the human has to tail logs, check dashboards, scroll Slack, and read PRs to know what the agent is doing, you've shifted overburden from the agent to the operator. Andon at the right granularity (one notification per action that needs human attention) prevents this.

### The trinity: when to apply which

| Symptom | Likely root cause | Family | Fix |
|---|---|---|---|
| Agent uses 10× the tokens it needs | Filler, re-reads, restating | Muda | Stripper at emission, dedup at retrieval |
| Reviewer queue is 50 PRs deep on Tuesday and 3 on Thursday | Bursty dispatch from the worker | Mura | `MaxItemsPerTick`, schedule levelling |
| Agent stalls / times out on long compositions | Asking the LLM to do too much in one shot | Muri | Decompose into multiple agents or offload to Python |
| Agent re-runs the same `git status` 5 times | No session-scoped cache for deterministic reads | Muda | Memoize within session |
| CI runner pool pegged for an hour after an agent burst | Push-shaped queue with no upstream cap | Mura | Heijunka — cap the worker rate |
| Reviewer says "I can't keep up" | Throughput exceeds review capacity | Muri | Cap dispatch, expand auto-merge surface |

### Anti-patterns

- **Treating Muda as bad and Mura as okay.** Mura compounds — every burst recovers slower than it spikes. Smoothing is a permanent investment, not a one-time clean-up.
- **Solving Muri by buying more capacity.** A reviewer overburdened by 30 PRs/day doesn't need a second reviewer; they need the agent to ship 10 PRs/day. The fix is upstream.
- **Confusing Muda with intentional slack.** The system needs slack to absorb variance. Lean is about waste, not about running at 100% utilisation. A worker that's idle 40% of the time is fine if that idle time absorbs spikes.

---

## 5S — workspace discipline as a precondition to good work

> *"Sort, Set in order, Shine, Standardise, Sustain. Workspace discipline as a precondition to good work."*

### 5S applied to the agent's workspace (the repo + the cache + the runtime)

| 5S | Meaning | Repo discipline equivalent |
|---|---|---|
| **Sort** (Seiri) | Keep what's needed, discard the rest | `.gitignore` of self-install junk, node_modules, vector indexes, packs (rlm-context-agent PR #23 was exactly this — added `/skills/`, `/.cursor/`, `/.gemini/`, `/.opencode/`, `/.claude/worktrees/` to gitignore) |
| **Set in order** (Seiton) | Every tool has its place | Conventional layout: `cmd/<binary>/`, `internal/<package>/`, `assets/{agents,commands,skills}/` (relay) and `installer/`, `assets/`, `tests/`, `docs/` (rlm-context-agent) — predictable so the agent doesn't need to guess where things go |
| **Shine** (Seiso) | Keep it clean | Linter (ruff for Python, `go vet` for Go), pre-commit hooks; agent PRs that fail lint don't merge |
| **Standardise** (Seiketsu) | Agree on conventions and document them | `CLAUDE.md` / `AGENTS.md` style files that codify the team's conventions for the agent to follow; `SKILL.md` files for repeated workflows; shared frontmatter format across all agent files |
| **Sustain** (Shitsuke) | Keep doing it | CI that runs the linter on every PR; Honda Construct rules in the engine; the harness lock |

### Why this is non-negotiable for autonomous agents

The repo is the agent's workspace. A messy repo produces messy agent output. A repo with inconsistent file layouts forces the agent to spend tokens orienting itself; a repo with strict conventions lets the agent reason at the pattern level. 5S is the upstream investment that pays off on every subsequent agent session.

The relay codebase's commit history shows this discipline in practice: `fix(installer): use absolute import in __main__`, `chore(gitignore): cover self-install artifacts and subagent worktrees`, `feat(construct): enforce Honda-inspired agentic principles in relay engine`. Each commit either *adds* a convention, *enforces* a convention, or *cleans up* a violation. None is a sloppy "fix bug" with no scope.

### The convention-as-instruction loop

When an agent reads a `CLAUDE.md` or `AGENTS.md` at session start, it's reading the team's standardised work instruction. When the agent writes a file in a different shape than the convention, the linter catches it; CI catches the linter failure; the PR doesn't merge. The 5S loop closes mechanically.

### Anti-patterns

- **One-off conventions.** A team that decides to use `snake_case` in some files and `camelCase` in others has no Seiketsu — the standard is unstable, so the agent has no signal to follow.
- **Committed `.env` files.** Sort failure. The agent will see the file and reason from it; a file containing secrets in the workspace is a leak waiting to happen.
- **Letting the agent define the conventions.** The agent's "best guess" today is unstable across sessions. Conventions need a human-decided baseline that is more stable than any single agent reasoning trace.

---

## Standardised work

> *"Define the best-known method, follow it until you find a better one, then update the standard."*

### The exec plan template as standardised work

The exec plan from the unattended-agent architecture is the agent's standardised-work instruction sheet. Every session starts by reading it; every session ends by updating it. The seven fields:

1. **Milestone** — the larger goal the slice contributes to
2. **Next slice** — the one thin unit of work this session will ship
3. **Proving test** — the test that, if green, demonstrates the slice is done
4. **Lint command** — the standardised gate the diff must pass
5. **Expected red** — what the failing test should look like before the slice is implemented
6. **Files in scope** — the explicit set of files the slice may modify
7. **Validation evidence** — how to confirm the slice integrates correctly

This is exactly the shape of a Toyota assembly-station instruction sheet. Each field constrains the work; together they ensure that two operators (or two agent sessions) doing the same slice would do it the same way.

### SKILL.md files as standardised work for whole workflows

Each SKILL.md in the rlm-context-agent codebase codifies the best-known sequence for one job, written so an agent can follow it verbatim:

- `/rlm` — recursive language model retrieval
- `/work` — work-graph state mutations
- `/library` — knowledge-pack vector search
- `/pr-review-triage` — bot review-comment triage
- `/large-text` — bulk text ingestion + indexing
- `/books` — PDF library deep-dive

When the standard is wrong, you update the standard — you do not let the agent improvise. Improvisation looks like initiative; under autonomous operation it looks like drift.

### Sub-agent contracts as standardised work at the worker level

Every sub-agent has a narrow contract with bounded inputs, structured JSON outputs, refusal codes, no scope creep. Examples from the codebases:

- `rlm-subcall-{low,med,high}` — read one chunk, return JSON with `relevant`, `evidence`, `confidence`, `missing`
- `github-ops`, `jira-ops`, `linear-ops`, `azdo-ops` — execute one verb against one provider, return JSON with `verb`, `ok`, `result`, `preconditions_checked`, `next_suggested_verbs`
- `pr-reviewer` — triage one review comment, return `{comment_id, category, confidence, reasoning, suggested_action, evidence}`

Each contract is documented at the top of the agent's markdown file; each contract is testable; each contract is the same shape across providers (which makes the orchestrator simpler).

### The PTCF prompt blueprint as standardised work for prompts

From `ai-agents.md`, the PTCF framework is standardised work applied to prompts:

| Component | Purpose | Example |
|---|---|---|
| **Persona** | Defines the agent's identity and expertise level | "You are a senior security engineer..." |
| **Task** | Specifies the exact action required | "Review this code for SQL injection vulnerabilities" |
| **Context** | Provides domain knowledge and constraints | "This is a Node.js API that queries PostgreSQL" |
| **Format** | Constrains output structure | "Return a JSON array of findings with severity and line number" |

Anti-pattern (also from the source): merging system and user concerns into a single prompt. This makes personas inconsistent and outputs unpredictable.

### Anti-patterns

- **Wiki-page standardised work.** Standardised work in TPS is the *thing the operator is doing right now*, posted at the workstation, in their hands. The exec plan in the issue body is standardised work; a `docs/HOW-WE-RUN-AGENTS.md` that nobody opens is decoration.
- **Standards updated at random.** The standard is updated when the team has evidence the old standard was wrong. Random updates destabilise everyone downstream — the agent loses the signal.
- **Per-agent standards.** Different sub-agents enforcing different conventions on the same artifact (PR description, commit message, log format) means there is no standard. Pick one shape and apply it across all the sub-agents.

---

## SMED — rapid changeover

> *"Single-Minute Exchange of Die. Reduce setup time so changeovers stop dominating the production schedule."*

### Setup time in agent ops

Three loci where setup happens, three loci where SMED applies:

1. **Idempotent installers.** `python -m installer inject` skips on cache hit; `extract_per_book.py` skips outputs newer than inputs; `relay-worker` skips items whose markers say not-ready. Setup happens once; subsequent invocations are zero-cost.
2. **Knowledge-pack cache.** `~/.rlm_cache/packs/<name>/<version>/` is downloaded once and shared across every target repo on the machine. Setup-per-project drops from "download 360 MB" to "symlink path." Multiple versions of the same pack coexist, so different target repos can pin different versions without re-download.
3. **Hot-reloaded fixtures during eval.** Load the LanceDB index at process start; run all queries against the same in-memory handle. Setup amortised across the test run.

### SMED at the workflow level

Marker-file resume: when a `blocked` issue is unblocked, the next tick picks up *exactly where the previous session stopped*, no re-bootstrap. The exec plan was written to disk in the issue body before the agent stopped; the new session reads it and continues from the next slice.

This is SMED applied to agent sessions: no warm-up; no context reconstruction; the standardised work instruction is right there waiting.

### Why long setup discourages experimentation

A setup time of "I'll re-index the whole knowledge pack every time I tweak a prompt" is what kills kaizen. With SMED — cached packs, idempotent installers, marker-file resume — it becomes cheap to try a new pattern, evaluate it, keep or discard. Without SMED, every experiment costs an hour, so experiments don't happen, and the system stops improving.

### Anti-patterns

- **Re-downloading on every run.** A cache that doesn't survive process restart is not SMED — it's the same setup cost amortised over multiple invocations.
- **State reconstruction from logs.** "Just re-read the last 100 log lines to figure out where you were" is the opposite of SMED. The exec plan in the issue body is the SMED-friendly alternative.
- **Restart-as-recovery.** Restarting the worker on every blocked-on-human → unblocked transition forces a setup cost. The systemd-supervised long-running mode amortises that across many ticks.

---

## Genchi Genbutsu — go and see for yourself

> *"Go to the actual place. See the actual thing. Trust your own eyes over the report."*

### Direct in agent ops — every retrieval pattern that beats summary-of-summary

**RLM** is genchi genbutsu for context windows. The root LM doesn't read someone else's summary of the corpus, it reads the corpus itself via a sub-LM that returns evidence with citations. The 5/5 retrieval validation on the books pack proved the difference: vector search returns the actual chapter, not a derivative description of it.

**Per-book deep extracts** preserve the source's original technical substance instead of rewriting it. When the agent needs the exact `podman secret create` syntax, it gets the actual command, not a paraphrase. The 93%-retention number from `extract_per_book.py` is the measure of how literally the source was preserved.

**Agent reads the issue body, not someone's summary of it.** The `relay-worker` `GetExecPlan` returns the issue's literal body. The agent runs against ground truth, not a translation.

**`journalctl -u relay-worker`** — the operator reads the actual log lines, not a dashboard summary of "5 failures, all similar." When something looks weird, you go to the source.

### The Provenance component

The `ai-agents.md` Knowledge Retrieval Agent design names a specific component for this:

> **Provenance component** — tracks which retrieved passages contributed to each response, enabling citation and auditability.

Without provenance, the agent's output drifts from its sources at every step; with provenance, every claim can be traced back to its genbutsu (the actual passage). The pattern is the architectural form of genchi genbutsu: build the audit trail in, automatically.

### Citation verification as a discipline

The Scientific Discovery Agent (`ai-agents.md`) names the dominant failure mode of the genre: **hallucinated citations**. The mitigation: ground every claim in a retrieved passage with DOI; use a citation verifier tool that resolves DOIs before including them in the output.

The same pattern applies in legal: the Legal Intelligence Agent's citation verification step resolves every case citation before including it in the output. Use a DOI/case number resolver tool; reject unresolvable citations.

These are jidoka + genchi genbutsu combined: the agent verifies its own output against ground truth and refuses to ship the unverifiable.

### The opposite — why summary-of-summary fails

Letting an agent or a human operate from layered summaries is how drift compounds. At each layer of summary, signal is lost; at each layer it's also a place where the summarising actor might be wrong. Genchi Genbutsu cuts the chain.

The `ai-agents.md` Verification and Validation Agent operationalises this with NLI (natural language inference) checks: every claim is compared against retrieved evidence using a model trained for exactly this task (`facebook/bart-large-mnli` is the typical choice). When sources disagree, **report uncertainty rather than hallucinate resolution**.

### Anti-patterns

- **Summary as canon.** A team that treats the agent's last summary as authoritative — without re-grounding in the source — has lost genbutsu. The summary is a derivative; the source is canon.
- **Quote-without-citation.** An agent that paraphrases its retrieved chunks but doesn't attribute them gives the user no path back to the source. This violates provenance and breaks the kaizen loop (you can't refute what you can't find).
- **Trust the agent's belief about a fact.** "The model is confident this is the right answer" is not genjitsu; the actual passage that supports it is.

---

## Hansei — honest reflection

> *"Honest reflection on what went wrong, even when it succeeded. Especially when it succeeded."*

### Reflection structures in agent ops

Three concrete loci:

1. **The `/pr-review` skill** is hansei applied to bot PR comments — every comment evaluated, every claim verified against the actual code, every thread either fixed or pushed back with reasoning. Refusing to silently ignore is the discipline. The categorisation (`fix-now / fix-followup / push-back / clarify-and-resolve / wontfix`) forces every comment into a decision; the reasoning field forces evidence; the resolve-only-when-acted rule forces accountability.
2. **The eval harness** measures over time. Hansei requires evidence; eval supplies it. `relay-eval`'s UCB-driven optimization is hansei built into the loop: the system tracks per-prompt outcomes, surfaces the underperformers, drives kaizen on them.
3. **Security review skill** — read the diff with adversarial intent, find the issues you would have shipped past in the rush. The Toyota practice: even when a launch succeeds, you hold a hansei meeting and identify what could have been better. The agent equivalent: even when the PR merges green, the agent's exec plan should record what surprised it, what slowed it down, what it would do differently.

### Hansei in PR descriptions

PR descriptions that report what was done **and what was considered and rejected** preserve the reasoning for future-you. The convention has three sections:

- **Summary** — what changed, in 1–3 bullets.
- **Test plan** — how to verify it works.
- **Why this shape** — what alternatives were considered and why they were rejected.

The third section is the hansei. It's the future-self reading the PR three months later who benefits.

### Hansei loops in the AI-agents literature

The Code Generation chapter of `ai-agents.md` describes the "refinement loop" pattern: when the test fails, the developer agent gets the failing-test output as feedback and tries again. Up to three iterations; on the third failure, escalate. This is the smallest possible hansei loop — three rounds of "try, examine the failure, try again," then surface to a human.

The TDG (Test-Driven Generation) workflow makes hansei mandatory:

```
user_story → task_decomposition → [for each task]:
  test_synthesis → code_synthesis → execution →
  [if PASS] → next_task
  [if FAIL, iterations < 3] → refinement_loop → code_synthesis
  [if FAIL, iterations >= 3] → escalate
```

The escalate path is the andon; the refinement loop is hansei.

### Anti-patterns

- **Ship-and-forget.** A PR that merges and is never reviewed in retrospect provides no kaizen substrate. Even green PRs deserve a five-minute hansei.
- **Hansei without action.** Reflection that doesn't update the standardised work is therapy, not engineering. Each hansei should produce either an updated exec plan, an updated SKILL.md, an updated CI rule, or a follow-up issue.
- **Hansei only on failure.** Toyota practice: hold the hansei meeting after the *successful* launch too. Successful runs hide the latent failures that will compound.

---

# Part II — Honda-specific contributions

Toyota wrote the Production System; Honda layered its own philosophy on top.

## The Three Joys

> *"The joy of buying. The joy of selling. The joy of creating."*

Honda's framing of who the work is for. Translated to agent ops:

| Honda's joy | Agent-ops translation |
|---|---|
| **Joy of buying** | The user (developer) gets time back — the whole point. The agent runs while the developer does something else. |
| **Joy of selling** | The maintainer (you) ships visible value — the PRs merge, the system stays coherent, the metrics improve. |
| **Joy of creating** | The agent's outputs feel *right* — small clean PRs, clear commit messages, exec plans that read like a craftsperson's notes. |

If any of the three joys is absent, something is wrong:

- If the agent ships PRs but the developer is supervising every one → no joy of buying. Layer 1 (OS) is failing.
- If the agent saves time but produces incoherent slop → no joy of selling. Layer 2 (Harness) is failing.
- If the work is correct but the diffs are mechanical and unreadable → no joy of creating. Standardised work is missing the craft dimension.

Joy is a vague KPI on purpose — Honda used it to mean "if you'd be embarrassed to show this work to a craftsperson, fix it." Agent ops needs the same standard.

## Sangen Shugi — the three reals

> *"The three reals — genba (the actual workplace), genbutsu (the actual thing), genjitsu (the actual facts)."*

Sangen Shugi is the umbrella for Genchi Genbutsu plus two extensions:

- **Genba** — *the actual workplace*. For agents, this is the **isolated VM**, not the developer's laptop. Production-similar, with real services, real tokens, real environment variables. Decisions made in the genba are valid; decisions made on a hand-curated dev box are not.
- **Genbutsu** — *the actual thing*. The repo state, the CI run, the failing test output. Not the agent's *report* of the test output; the actual `target/test-results.xml`.
- **Genjitsu** — *the actual facts*. Numbers, not vibes. P95 latency from the eval harness; lint-error count from CI; merge-throughput from the GitHub API. Agents that report "I think this looks better now" without evidence are not operating in genjitsu.

Sangen Shugi is the discipline that makes the andon signal meaningful — an andon based on the agent's *belief* about a problem is noise; an andon based on a verifiable fact is signal.

## Wai-Gaya — flat-hierarchy structured argument

Honda's internal practice of long, structured, flat-hierarchy argument until consensus emerges. Less famous than the other principles, but directly applicable to multi-agent systems.

The `ai-agents.md` Multi-Agent Systems chapter describes consensus engines and adversarial-critic patterns. The Wai-Gaya analogue: agents argue structured positions, the flat-hierarchy means no agent has decision authority over the others, and the argument continues (with a bounded round count) until a consensus score crosses a threshold. The `ConsensusEngine` pattern from the source:

```python
class ConsensusEngine:
    def run_consensus(self, problem, max_rounds=3):
        proposals = [agent.propose_solution(problem, context) for agent in self.agents]
        for round_num in range(max_rounds):
            critic_idx = round_num % len(self.agents)
            self.agents[critic_idx].set_role("adversarial_critic")
            evaluations = [
                agent.evaluate_proposal(p, problem)
                for agent in self.agents for p in proposals
                if p.agent_id != agent.id
            ]
            scores = self._compute_consensus_scores(proposals, evaluations)
            if self._has_converged(scores, tolerance=0.5):
                return self._synthesize(proposals, evaluations, scores)
            proposals = self._refine_proposals(proposals, evaluations, context)
```

The Condorcet Jury Theorem (also from `ai-agents.md`) supplies the theoretical underpinning: if each agent independently makes the correct decision with probability p > 0.5, then the probability that the majority is correct increases toward 1 as the number of agents grows. **Key requirement: agent errors must be independent** — correlated errors eliminate the benefit. Wai-Gaya structure (mandatory adversarial critic, expertise-weighted voting, cross-pollination prompting) is what enforces independence.

---

# Part III — The composite operating model

## Layer mapping — principles × architectural layers

The unattended-agent architecture's three layers each enforce a specific subset of the principles:

| Layer | Component | Principles enforced |
|---|---|---|
| **OS** | systemd unit + timer | Andon (journal), Heijunka (cron cadence), SMED (process restart is cheap) |
| **OS** | The shell wrapper / `relay-worker` | Standardised work (the script *is* the standard for one tick), Pull (only acts when markers say to) |
| **OS** | Isolated Linux VM | Genba (production-similar workplace) |
| **Harness** | Red/green/refactor loop | Standardised work (the rhythm), Kaizen (one slice at a time) |
| **Harness** | Exec plan document | Standardised work (the template), Hansei (updated after each slice) |
| **Harness** | Harness lock CI | Poka-yoke (agent cannot weaken its own constraints), Jidoka (CI rejects automatically) |
| **Harness** | Branch protection + auto-merge | Poka-yoke (no merge without green), Jidoka (the gate stops the line) |
| **Harness** | Tool capability surface | Poka-yoke (limited blast radius), Muri avoidance (tools sized for what's bounded) |
| **Persistence** | Marker files / labels | Andon (visible state), Pull (markers gate the next tick) |
| **Persistence** | Exec plan in the repo | Standardised work, Genbutsu (the actual plan, not a memory of it) |
| **Persistence** | Issue / ticket comments | Andon (the audit trail), Hansei (reflection captured for next time) |
| **Persistence** | Linked PRs | Genbutsu (the actual code change) |

Adding a principle (say, a new poka-yoke check) is a matter of identifying which layer it belongs in and dropping it in. The model scales additively.

## The complete artifact stack

```
┌──────────────────────────────────────────────────────────────────────┐
│  Issue tracker (GitHub Issues / Jira / GitLab / Trello)              │
│    Labels:   ready-for-agent, agent-working, blocked-on-human, stop  │
│    Body:     exec plan (milestone, next slice, proving test, …)      │
│    Comments: agent audit trail (andon)                               │
│    PRs:      units of progress (genbutsu)                            │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  relay-worker  (cmd/relay-worker)                                    │
│    Cron / systemd-driven (heijunka)                                  │
│    Provider-agnostic via WorkSource interface                        │
│    Marker claim + release on every tick (poka-yoke)                  │
└────────────────┬─────────────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  relay-server  agent session                                         │
│    Bounded by --agent-timeout (muri prevention)                      │
│    Tools: bash, read_file, write_file, math (capability surface)     │
│    Stream: structured outcome → comment + plan update + marker shift │
│    Construct rules:  MudaStripper, sensitive-data guard              │
└────────────────┬─────────────────────────────────────────────────────┘
                 │ (when knowledge needed)
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Knowledge pack  (rlm-context-agent inject + ~/.rlm_cache)           │
│    Static markdowns under .claude/knowledge/  (zero-latency)         │
│    Vector DB at ~/.rlm_cache/packs/<n>/<v>/vectordb/  (deep-dive)    │
│    /library slash command bridges the two                            │
└────────────────┬─────────────────────────────────────────────────────┘
                 │ (when context too big)
                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  RLM sub-call  (rlm-subcall-{low,med,high} per complexity)           │
│    Reads ONE chunk, returns structured JSON  (genchi genbutsu)       │
│    Rank-parallel dispatch via root LM  (heijunka of compute)         │
└──────────────────────────────────────────────────────────────────────┘
```

Every layer is doing the work of one or more TPS principles. None of them is doing more than one or two — that's how each stays simple and testable.

## The lifecycle of one agent slice — annotated

A single slice walked through the operating model, with each step tagged by principle:

| Step | Action | Principle |
|---|---|---|
| 1 | Human files an issue with `ready-for-agent` label and an exec plan in the body | Standardised work (the plan); JIT (the label is the pull signal) |
| 2 | Cron timer fires `relay-worker` | Heijunka (the takt cadence) |
| 3 | Worker calls `WorkSource.ListReady` — finds the issue | JIT (pull from queue) |
| 4 | Worker calls `SetWorking` — applies `agent-working` label | Poka-yoke (claim prevents double-pickup) |
| 5 | Worker reads the exec plan via `GetExecPlan` | Genbutsu (the actual plan, not a cached belief) |
| 6 | Worker dispatches to `relay-server` agent endpoint with the plan | Standardised work (the prompt template) |
| 7 | Agent thinks → acts → observes → repeats (ReAct) | Standardised work (the per-turn loop) |
| 8 | Each tool call goes through the capability surface | Poka-yoke (bounded blast radius) |
| 9 | `MudaStripper` filters filler from the output stream | Muda elimination (at emission) |
| 10 | Agent writes the failing test, then the production fix | Kaizen (one thin slice) |
| 11 | Agent runs the lint command and the proving test locally | Genchi genbutsu (verify against the actual gate) |
| 12 | Agent opens a PR with a clear description | Standardised work (the PR template) |
| 13 | CI runs the full test suite + harness-lock check + linter | Poka-yoke (mechanical gates) |
| 14 | If CI green → auto-merge | Jidoka (the gate makes the call) |
| 15 | Agent posts a progress comment summarising the slice | Andon (audit trail) |
| 16 | Agent updates the exec plan body to reflect what shipped | Standardised work (update the standard); Hansei (note what surprised it) |
| 17 | Worker calls `ClearWorking` — removes the `agent-working` label | Poka-yoke (release the claim) |
| 18 | Worker exits cleanly; next tick repeats | SMED (no warm-up needed for next session) |

If any step fails:

- Step 6–13 fail → agent calls `Block` with the reason. `blocked-on-human` label applied; comment posted; worker exits cleanly. Next tick skips this issue. Human resolves; removes the label; tick picks up where it stopped.
- Step 14 fails (CI red) → no merge; the agent's PR sits with a red status check until the agent (or a human) pushes a fix.
- Step 17 fails (clear failed) → logged as warning; the next tick may double-process if the label isn't cleared by the human or by a janitor job. Documented limitation; the multi-worker safety section covers this.

---

# Part IV — Agent engineering practices, mapped

This section catalogues substantive technical patterns from `ai-agents.md` that map onto the Honda Construct frame — the patterns the operating model is built to host.

## Cognitive architecture choices

Five interaction paradigms, ordered by complexity:

| Paradigm | Description | Honda Construct fit |
|---|---|---|
| **Direct LLM interaction** | Single prompt → single inference. No memory, no tools, no planning. | Adequate for one-shot question answering; not for unattended ops. |
| **Proxy agent** | Lightweight wrapper for routing, formatting, schema enforcement. | The relay agent endpoint; consistent shape without multi-step reasoning. |
| **Assistant system** | Tool-augmented helper with session memory + function calling. | The dominant pattern for in-IDE copilots; not the unattended-worker shape. |
| **Autonomous agent** | Long-term goals, task decomposition, tool selection, loop until satisfaction. | The unattended-worker shape. Key KPIs: task completion rate, replanning frequency, goal drift rate. |
| **Multi-agent system (MAS)** | Multiple specialised agents coordinating through shared memory or message passing. | Wai-Gaya territory; consensus engines; supervisor patterns. |

The five-level Agentic AI Progression Framework (`ai-agents.md`):

| Level | Name | Characteristics |
|---|---|---|
| 0 | Manual operations | Human executes all steps |
| 1 | Reactive agents | Responds to input, no planning |
| 2 | Tool-using agents | Selects and invokes external tools |
| 3 | Planning agents | Multi-step task decomposition |
| 4 | Learning agents | Closed-loop self-improvement |

The Honda Construct operating model fits Level 3 → Level 4. Level 1–2 don't need the architecture; Level 4 needs the eval harness for the closed loop.

The SMPA (Sense-Model-Plan-Act) abstraction:

```python
class Agent(ABC):
    def execute(self, input_data: Dict[str, Any]) -> Any:
        sensed   = self.sense(input_data)
        modeled  = self.model(sensed)
        planned  = self.plan(modeled)
        result   = self.act(planned)
        return result
```

This is the per-turn standardised work loop.

## Memory hierarchies

Four memory types from `ai-agents.md`:

| Type | Analog | Persistence | Implementation |
|---|---|---|---|
| Working memory | RAM | Session | `ConversationBufferMemory` |
| Episodic memory | Personal diary | Long-term | Vector DB + timestamp |
| Semantic memory | Encyclopedia | Long-term | Vector DB |
| Short-term summary | Executive briefing | Session | `ConversationSummaryBufferMemory` |

The Memory-Augmented Agent Architecture: three layers working in concert.

1. Working memory — active context window for current task state.
2. Episodic memory — timestamped event log (supports "what did the user say last week?").
3. Semantic memory — embedding-indexed knowledge base for similarity retrieval.

**Tradeoff:** more memory layers improve personalisation and recall but increase latency, storage cost, and retrieval complexity. Episodic memory requires TTL policies to prevent unbounded growth.

The Honda Construct angle: **don't load all memory into context for every turn**. Working memory carries the immediate task; episodic memory is queried only when relevant; semantic memory (the knowledge pack, the vector index) is consulted on-demand via tool calls. This is heijunka applied to context tokens — load only what the current operation needs.

The Dual-Memory Hierarchy pattern (used in the Empathetic Mental Health Support Agent case study) combines a `ConversationSummaryBufferMemory` for working state with a FAISS vector DB for semantic retrieval. The handler is concise:

```python
def handle_query(self, user_input: str):
    if not self.safety.is_safe(user_input):
        return self.safety.get_crisis_protocol()
    history = self.context.working_memory.load_memory_variables({})['history']
    full_context = [self.system_prompt] + history + [HumanMessage(content=user_input)]
    response = self.llm.invoke(full_context)
    self.context.working_memory.save_context(
        {"input": user_input}, {"output": response.content}
    )
    return response.content
```

The safety check is first — jidoka on the input.

## Tool-use and function-calling

The Tool-Using Agent Pattern has four components:

- **Reasoning core** — the LLM that decides which tool to call and with what arguments.
- **Tool registry** — catalog of available tools with schemas.
- **Execution engine** — invokes the selected tool and returns the result.
- **Tool chest** — the actual implementations.

The Selection Funnel — a multi-stage narrowing:

1. Intent classification (broad category filter).
2. Semantic search over tool registry (candidate ranking).
3. Constraint filtering (final verification against parameter types).

This is poka-yoke at the tool boundary — the agent literally cannot reach a tool that fails the constraint filter.

Error handling — common failure modes are timeout, invalid parameters, API rate limit, downstream service unavailable. The architectural recovery strategies from `ai-agents.md`:

- **Retry with exponential backoff** (using `tenacity`):

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def call_external_api(payload):
    return requests.post(ENDPOINT, json=payload, timeout=5)
```

- **Graceful degradation:** return a cached result, a lower-quality fallback, or an explicit "I cannot complete this" response. **Never silently swallow errors in agentic pipelines.**

The Honda Construct framing: silent error swallow is jidoka failure. Either the agent fixes it, falls back explicitly with andon, or stops.

MCP (Model Context Protocol) is the standardised work for tool discovery + invocation across providers. Three phases: discovery, capability description, invocation. The schema for a capability is JSON-Schema:

```json
{
  "name": "SearchFlights",
  "description": "Search available flights between two airports",
  "input_schema": {
    "type": "object",
    "properties": {
      "origin": {"type": "string"},
      "destination": {"type": "string"},
      "departure_date": {"type": "string", "format": "date"}
    },
    "required": ["origin", "destination", "departure_date"]
  }
}
```

A2A (Agent-to-Agent) is the analogous standardised work for delegation across agents — versioned, schema-described, contract-based.

## Multi-agent coordination

Three collaboration architectures from `ai-agents.md`:

- **Supervisor pattern** — one orchestrator agent manages a team of specialists. The supervisor routes tasks, aggregates results, manages the conversation flow. (This is the assembly-line shape lifted to agents.)
- **Peer-to-peer** — agents communicate directly through a shared message bus. No central coordinator; emergent coordination.
- **Chain-of-agents orchestrator** — agents form a pipeline; each enriches state for the next. Natural for sequential document processing.

The Memory-Augmented Multi-Agent System adds shared state:

- **Working memory (short-term context)** — shared conversation state in the current session.
- **Long-term memory (knowledge base)** — shared vector DB for cross-session knowledge.

Conflict resolution when multiple agents produce conflicting outputs (this is the Wai-Gaya territory):

1. **Arbitration by confidence** — select the output with the highest calibrated confidence score.
2. **Majority voting** — take the plurality answer across N agents.
3. **Weighted voting** — weight votes by each agent's historical accuracy on this task type.
4. **Adversarial critic** — a dedicated critic agent challenges the leading proposal; the final answer must survive the critique.

Concrete arbitration architecture:

```python
class ConflictArbiter:
    def resolve(self, proposals: List[AgentProposal]) -> AgentProposal:
        scored = [(p, self.confidence_scorer.score(p)) for p in proposals]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_proposal, top_score = scored[0]
        if top_score < self.confidence_threshold:
            return self.escalate_to_human(proposals)
        return top_proposal
```

The escalate path is jidoka. If consensus can't be reached at sufficient confidence, the line stops.

The E-Commerce Order Processing case study describes a five-agent workflow:

- **Intake agent** — validates order data
- **Classifier agent** — routes by product type
- **Validator agent** — checks inventory and pricing
- **Payout agent** — processes payment
- **Escalation agent** — handles exceptions

Each agent is a station; the workflow is the assembly line. The escalation agent is the andon-puller of last resort.

The Multi-Agent Insurance Claims Workflow shows the same pattern with conditional routing:

```
Claim CLM-4821 path:
intake_agent → classifier_agent → validator_agent →
  [if fraud_suspected] → escalation_agent
  [if approved]        → payout_agent
```

## Confidence calibration and refusal

Calibrated confidence — raw model scores are not probabilities. From `ai-agents.md`:

- **Platt scaling (temperature scaling)**: `p_calibrated = sigmoid((logit(p_raw) - b) / T)`. T > 1 flattens; T < 1 sharpens. Tune T on a held-out calibration set.
- **Brier score**: `BS = (1/N) Σ (p_i - o_i)²`. Lower is better; 0.0 is perfect.
- **Reliability diagrams**: visual diagnosis of overconfidence vs underconfidence.

Epistemic vs aleatoric uncertainty:

- **Epistemic** — uncertainty from insufficient training data; reducible with more data.
- **Aleatoric** — inherent randomness in the task; irreducible.

The Honda Construct angle: the escalation threshold (jidoka trigger) must be tuned to *calibrated* confidence, not raw scores. An over-confident raw score will silently bypass the andon.

The ConfidenceAwareAgent emits the full hypothesis space:

```python
class ConfidenceAwareAgent:
    def reason_with_confidence(self, query, context):
        hypotheses = []
        for _ in range(self.n_hypotheses):
            result = self.generate_hypothesis(query, context)
            raw_score = self.score_hypothesis(result, context)
            calibrated = self.calibrator.calibrate(raw_score)
            hypotheses.append({
                'answer': result,
                'confidence': calibrated,
                'evidence': self.gather_evidence(result, context)
            })
        hypotheses.sort(key=lambda h: h['confidence'], reverse=True)
        return hypotheses
```

## Domain-specific agent architectures

From `ai-agents.md`, multiple domain examples — each layered on the same operating-model bones with domain-specific stations.

**Healthcare Intelligence Agent** — four-layer architecture:

1. **Ingestion** — ingest EHR, lab results, imaging reports; normalise to FHIR standard.
2. **Knowledge** — medical ontologies (SNOMED, ICD-10), drug databases, clinical guidelines.
3. **Reasoning** — Bayesian belief updating, POMDP for decision under uncertainty.
4. **Explanation** — calibrated confidence, plain-language rationale, citation to clinical guidelines.

Bayesian belief update:

```python
def update_belief(belief, observation, likelihood_model):
    """Bayesian belief update: P(s|o) ∝ P(o|s) * P(s)."""
    likelihoods = np.array([
        likelihood_model[diag].score(observation)
        for diag in likelihood_model
    ])
    posterior = likelihoods * belief
    return posterior / posterior.sum()
```

POMDP in clinical context: the agent cannot observe the true disease state directly. It maintains a belief distribution over possible diagnoses, updated as new test results arrive. **Edge computing for privacy:** run the inference layer on-device or on a hospital-local server. PHI never leaves the institution. (Same pattern as the agent's isolated VM — keep PHI in genba.)

**Scientific Discovery Agent** — literature synthesis in three phases:

1. **Broad search** — async multi-source retrieval (arXiv, PubMed, Semantic Scholar).
2. **Quality filtering** — deduplication, citation count threshold, recency weighting.
3. **Synthesis** — identify consensus positions, note conflicts, flag open questions.

The dominant failure mode: hallucinated citations. Mitigation: ground every claim in a retrieved passage with DOI; use a citation verifier tool.

Hypothesis generation via abduction:

```python
def generate_abductive(self, observations, background_knowledge):
    candidates = []
    for obs_pair in combinations(observations, 2):
        gap = self.gap_detector.find_connecting_mechanism(obs_pair, background_knowledge)
        if gap.is_novel:
            h = Hypothesis(
                claim=gap.mechanism,
                supporting_observations=list(obs_pair),
                falsifiability_score=self.falsifiability_scorer.score(gap.mechanism)
            )
            candidates.append(h)
    return sorted(candidates, key=lambda h: h.falsifiability_score, reverse=True)
```

The falsifiability score is the genjitsu-friendly ranking criterion: hypotheses worth testing are those that can be disproven.

**Financial Advisory Agent** — risk metrics:

| Metric | Formula | Threshold |
|---|---|---|
| VaR (Value at Risk) | P(loss > VaR) = α | 5% daily |
| CVaR (Conditional VaR) | E[loss \| loss > VaR] | 10% daily |
| Maximum drawdown | max (peak − trough) / peak | < 20% |
| Sharpe ratio | (R_p − R_f) / σ_p | > 1.0 |

Compliance-by-architecture — regulatory constraints (suitability, fiduciary duty, disclosure) are enforced as hard constraints in the state machine, not as post-hoc LLM checks. An agent cannot produce an investment recommendation without passing a compliance node. (Poka-yoke at the workflow level.)

**Legal Intelligence Agent** — hybrid search with authority + recency weighting:

```python
def hybrid_search(self, query, jurisdiction=None, min_authority=0):
    query_embedding = self.embedder.encode(query)
    results = self.store.query(embedding=query_embedding, filter=filters, top_k=50)
    for result in results:
        authority_boost = result.metadata["authority_level"] / 10.0
        recency_boost = self._recency_score(result.metadata["date"])
        result.final_score = (
            0.5 * result.similarity_score
            + 0.3 * authority_boost
            + 0.2 * recency_boost
        )
    return sorted(results, key=lambda x: x.final_score, reverse=True)
```

Precedent finding — three-stage:

1. Semantic search for factually similar cases.
2. Authority ranking (Supreme Court > Circuit > District).
3. Recency weighting (more recent decisions carry higher weight absent contrary binding authority).

Every case citation is resolved before being included; unresolvable citations are rejected. (Genchi genbutsu: cite the actual case, never a hallucination.)

**Education Intelligence Agent** — POMDP again (the student's knowledge state is hidden), with Bayesian Knowledge Tracing:

```python
def bkt_update(p_mastery, correct, p_transit=0.1, p_slip=0.05, p_guess=0.2):
    if correct:
        p_correct_given_L     = 1.0 - p_slip
        p_correct_given_not_L = p_guess
    else:
        p_correct_given_L     = p_slip
        p_correct_given_not_L = 1.0 - p_guess
    p_obs       = (p_correct_given_L * p_mastery
                   + p_correct_given_not_L * (1 - p_mastery))
    p_posterior = (p_correct_given_L * p_mastery) / p_obs
    p_updated   = (p_posterior + (1 - p_posterior) * p_transit)
    return p_updated
```

Four BKT parameters: `p_mastery` (prior), `p_transit` (learning rate), `p_slip` (P(wrong | mastered)), `p_guess` (P(right | not mastered)).

Item Response Theory (IRT) 2PL — adaptive placement test:

```python
@staticmethod
def p_correct(theta, a, b):
    """2PL IRT model: a=discrimination, b=difficulty, theta=ability"""
    return 1.0 / (1.0 + math.exp(-a * (theta - b)))

def _information(self, item):
    """Fisher information at current theta estimate"""
    p = self.p_correct(self.theta, item['a'], item['b'])
    return (item['a'] ** 2) * p * (1 - p)
```

At each step, select the item with highest Fisher information at the current θ estimate. This maximises the information gained per question — JIT applied to assessment.

**Programming tutor case-study results from the source: 34% improvement in assessment scores; course completion 71% → 89%.** A measured kaizen outcome.

## Embodied agents — what physical-system constraints teach digital ones

Three properties physical agents face that digital ones don't (`ai-agents.md`):

1. **Irreversibility** — actions cannot be rolled back; worst-case planning is mandatory.
2. **Latency** — mechanical actuators introduce delays that are hard constraints, not QoS preferences.
3. **Energy limits** — onboard power is finite; every action has an energy cost that bounds the feasible plan space.

The **Asymmetric Control Loop** separates the system into two layers:

- **Reasoning layer** — asynchronous LLM-based agent that processes high-level intent and generates a plan.
- **Deterministic controller** — synchronous real-time loop that executes the plan while enforcing safety constraints.

The LLM provides "why" and "what"; the deterministic controller manages "how" within physical safety bounds.

This maps directly onto the unattended-agent architecture's split: the LLM (reasoning layer) writes the slice; the CI gates and harness lock (deterministic controller) enforce the safety constraints. The LLM cannot bypass the CI any more than a robot can bypass its emergency stop.

The four-layer control hierarchy:

| Layer | Abstraction | Frequency | Algorithm |
|---|---|---|---|
| Task Planning | Symbolic goals | 0.1–1 Hz | PDDL, LLM reasoning |
| Motion Planning | Collision-free paths | 1–10 Hz | RRT*, PRM |
| Trajectory Control | Time-parameterised path | 50–200 Hz | PID, MPC |
| Servo Control | Motor currents | 1–10 kHz | Current and torque loops |

The frequency split is the levelled-load — slow loops handle complex reasoning; fast loops handle deterministic control. Same shape as the unattended-agent architecture's slow outer loop (the agent session) wrapping a fast inner loop (the per-turn ReAct cycle).

The Admissible Action Set `A_safe(s)`: planning operates within this set. Control never executes actions outside it. The hardware emergency stop is the unconditional override that enforces it at the hardware level. (Poka-yoke at the lowest physical layer.)

---

# Part V — Agent orchestration patterns

## Five cookbook patterns, smallest to largest

From `agent-orchestration.md`:

1. **Headless minimal agent** — three primitives: create → send → stream events → wait. Every agent SDK has these.
2. **Headless agent CLI** — wraps pattern 1 with TUI, slash-command menu, local/cloud switch.
3. **Web app spawning cloud agents** — sandbox-per-user prototyping. Requires platform-level cloud sandboxes (or Daytona / Firecracker / container-per-agent fallbacks).
4. **Kanban for parallel agents** — board UI for tracking many running agents grouped by status / repo.
5. **DAG task runner with live canvas** — the headline pattern.

## The DAG runner — Heijunka of compute

The DAG runner's behaviour:

1. Author a JSON DAG describing the task: `title`, `tasks[]`. Each task has an id, a `depends_on` list, a `complexity` tier (`HIGH | MED | LOW`), and a self-contained `subtask_prompt`.
2. Validate: cycles rejected at parse, every `depends_on` must reference a real id.
3. Topo-sort using Kahn's algorithm into ranks.
4. For each rank: launch every task as a sub-agent concurrently (`Promise.all`). The runner stitches a 2,000-char snippet of every parent's output into the child's prompt automatically.
5. As each sub-agent streams events, the runner debounces writes to a `.canvas.tsx` file. The IDE hot-recompiles on every write.
6. Fail safe: timed-out task → `ERROR`; downstream skipped; SIGINT cancels all in-flight sub-agents and finalizes the canvas before exit.

DAG schema:

```json
{
  "title": "Build a tiny CLI todo app",
  "models": {
    "HIGH": "gpt-5.3-codex",
    "MED": "composer-2",
    "LOW": "auto-low"
  },
  "tasks": [
    {
      "id": "research-stack",
      "depends_on": [],
      "complexity": "LOW",
      "subtask_prompt": "Sketch the smallest reasonable design …"
    },
    {
      "id": "design",
      "depends_on": ["research-stack", "research-cli-conventions"],
      "complexity": "MED",
      "subtask_prompt": "Given the stack and conventions findings, write a one-page design doc."
    }
  ]
}
```

Cycle detection — iterative DFS with tri-color (`WHITE/GRAY/BLACK`) recursion stack. Topo-sort — Kahn's algorithm; returns ranks (each rank = tasks with no intra-rank dependencies).

The cookbook's quality bar:

> When you sketch the rank structure, at least one rank should contain more than one task in any non-trivial problem. If your DAG is a single chain of one-task ranks, you almost certainly missed parallelism — go back and look again.

Failure modes the runner handles:

| Failure | Handling |
|---|---|
| Task exceeds `--task-timeout-ms` | Marked `ERROR`; downstream skipped |
| No stream events for `--stream-idle-timeout-ms` | Marked `ERROR`; downstream skipped |
| Upstream task failed | Downstream marked `ERROR` with `Skipped: upstream task(s) failed` |
| SIGINT / SIGTERM / SIGHUP | Cancel all in-flight; finalize canvas with `CANCELED` |
| Unhandled promise rejection | Suppressed; uncaught exception triggers clean shutdown |

Each row is jidoka + andon: detect the defect, stop the affected work, surface the cause.

## Live-canvas hot-reload — Andon as a UI surface

Reference invocation:

```bash
cat > /tmp/dag.json <<'JSON'
{
  "title": "Refactor auth module",
  "tasks": [
    { "id": "audit", "depends_on": [], "complexity": "LOW",
      "subtask_prompt": "List every file in src/auth/ and summarise each in one line." },
    { "id": "find-callers", "depends_on": [], "complexity": "LOW",
      "subtask_prompt": "Grep the codebase for imports of src/auth/ and list each calling file." },
    { "id": "design", "depends_on": ["audit","find-callers"], "complexity": "MED",
      "subtask_prompt": "Propose a refactor plan that consolidates duplicated logic." },
    { "id": "implement", "depends_on": ["design"], "complexity": "HIGH",
      "subtask_prompt": "Implement the refactor described in the design." },
    { "id": "tests", "depends_on": ["implement"], "complexity": "MED",
      "subtask_prompt": "Add or update tests covering the refactored auth module." },
    { "id": "docs", "depends_on": ["implement"], "complexity": "LOW",
      "subtask_prompt": "Update README and the docs/ directory to match the new auth module." }
  ]
}
JSON
tsx run_dag.ts --init-only --dag /tmp/dag.json --canvas-path "$PWD/run.canvas.tsx"
tsx run_dag.ts            --dag /tmp/dag.json --canvas-path "$PWD/run.canvas.tsx"
```

The example has 4 ranks — `[audit, find-callers]` → `design` → `implement` → `[tests, docs]` — and runs in ~1m 47s end-to-end on a small repo using the default model map.

The "use anywhere" mapping — Cursor SDK, Claude Agent SDK, OpenAI Assistants, raw Anthropic SDK — is the platform-agnosticism that lets the same DAG-runner shape ride on any agent endpoint.

---

# Part VI — Data modeling for agent operations

The `data-modeling.md` source covers Snowflake-flavored warehouse design, but every principle there transfers to **how to structure the durable state the agent reads from and writes to**. The unattended-agent architecture treats the issue tracker as the state machine; once you commit to that, the state schema becomes a first-class design problem.

## Why dimensional rigour matters for agent state

The agent's exec plan is a record. The marker label is a state field. The audit-trail comments are events. The PRs are the units of progress. If you don't model these dimensionally, you cannot answer questions like "what's the agent's MTTR for blocked-on-human?" or "which complexity tier produces the highest first-time merge rate?"

The data-modeling source's four model types map to agent-state design work:

| Model type | Audience | Agent-ops example |
|---|---|---|
| Conceptual | Stakeholders | "Agent processes Issues; each Issue accumulates Comments and produces PRs" |
| Logical | Architects | Entity diagram with FKs: Issue → Comment, Issue → PR, Issue ↔ Marker (M:M via association) |
| Physical | Engineers | Postgres tables with PK, indexes, time-travel-equivalent (trigger-based audit) |
| Transformational | Data engineers | dbt models that flatten audit history into `fact_marker_transition` etc. |

Each stage adds detail. Conceptual answers *what exists*; logical *how it relates*; physical *how it is stored*; transformational *how it moves*.

## Grain — the most consequential decision

Kimball's first commandment: declare the grain of the fact table. The equivalent for agent ops: **declare the grain of an exec-plan slice**. Is one slice = one PR? = one commit? = one feature? Without a declared grain, the agent ships inconsistent units and review queues become impossible to estimate.

For agent telemetry, grain choices include:

| Fact table | Grain | Purpose |
|---|---|---|
| `fact_agent_session` | One row per agent session (per worker tick) | Throughput, duration, outcome |
| `fact_pr_outcome` | One row per PR | Merge rate, time-to-merge, lines changed, test-pass rate |
| `fact_marker_transition` | One row per marker change | Cycle time, blocked-on-human duration, MTTR for blocks |
| `fact_tool_call` | One row per tool invocation | Tool-mix per tier, retry rate, error rate |
| `fact_eval_score` | One row per (agent_version, prompt_id, eval_run) | Drift detection over time |

Each grain is the most atomic the source supplies. Aggregations roll up from the atomic grain; you cannot disaggregate from a coarser grain.

## Conformed dimensions — shared vocabulary across tools

Conformed dimensions: same dimension reused across fact tables for joinable analysis. The agent-ops equivalent: **the same vocabulary across tools**. `agent-working` should mean the same thing whether it's a GitHub label, a Jira status, a Trello list, or a relay marker. The `relay-worker` provider abstraction enforces this — the provider-agnostic `WorkSource` interface uses canonical names and per-provider adapters translate.

The bus matrix from `data-modeling.md` is the natural planning tool. Rows are facts; columns are dimensions; cells mark which facts use which dimensions:

```
                       | dim_date | dim_agent | dim_repo | dim_tool | dim_provider |
fact_agent_session     |    ✓     |     ✓     |    ✓     |          |      ✓       |
fact_pr_outcome        |    ✓     |     ✓     |    ✓     |          |      ✓       |
fact_marker_transition |    ✓     |     ✓     |    ✓     |          |      ✓       |
fact_tool_call         |    ✓     |     ✓     |          |    ✓     |              |
fact_eval_score        |    ✓     |     ✓     |          |          |              |
```

Conformed `dim_date`, `dim_agent`, `dim_repo` enable cross-fact analysis: "agents on repo X have higher session-duration on Tuesday" requires `dim_date` joined to both `fact_agent_session` and `fact_pr_outcome` consistently.

## Slowly-changing dimensions for agent state history

When an attribute changes over time, you keep history. From `data-modeling.md`:

| Type | Behavior |
|---|---|
| **SCD Type 0** | Retain original. No changes ever made. Use for stable reference data. |
| **SCD Type 1** | Overwrite. Lose history; only current state is queryable. |
| **SCD Type 2** | New row per change with effective-from/to dates. Full history. |
| **SCD Type 3** | Add a "previous value" column. Limited history (only one prior). |
| **SCD Type 6** | Hybrid — combines Type 1 + 2 + 3 in one table. |

The agent equivalent: **the exec plan is SCD Type 2**. The agent updates the body in place (the current value), but the issue's audit trail (comments + linked PRs) preserves the prior state. Future-you can reconstruct what the plan said three weeks ago by reading the comment thread.

The `dim_agent_version` table is naturally SCD Type 2 — when the model changes from sonnet-4-5 to sonnet-4-6, you don't overwrite the prior row, you close it (`__to_dts`) and open a new one (`__from_dts`). Then `fact_agent_session` joins to `dim_agent_version` via SK + effective-date so you can compare metrics across model versions.

## Fact-table patterns for agent telemetry

From `data-modeling.md`:

| Pattern | Description | Agent example |
|---|---|---|
| Transaction | One row per discrete event | One row per tool call, one per PR open, one per merge |
| Periodic snapshot | One row per entity per period | Daily summary of agent throughput |
| Accumulating snapshot | One row per process instance, updated as it progresses | One row per issue with timestamps for each lifecycle event |
| Factless | Records events with no numeric measures | Marker-applied events |
| Consolidated | Combines multiple processes for convenience | Sales + returns; sessions + PRs |

The accumulating snapshot is particularly natural for issue lifecycle:

```sql
CREATE TABLE fact_issue_lifecycle (
    issue_sk            NUMBER PRIMARY KEY,
    repo_sk             NUMBER,
    agent_version_sk    NUMBER,
    created_dts         TIMESTAMP_NTZ,
    ready_for_agent_dts TIMESTAMP_NTZ,
    first_agent_pickup_dts TIMESTAMP_NTZ,
    first_blocked_dts   TIMESTAMP_NTZ,
    last_unblocked_dts  TIMESTAMP_NTZ,
    closed_dts          TIMESTAMP_NTZ,
    final_outcome       VARCHAR,
    -- measures
    pr_count            NUMBER,
    blocked_seconds     NUMBER,
    cycle_time_seconds  NUMBER,
    agent_token_total   NUMBER
);
```

One row per issue. Updated as the issue progresses through lifecycle events. Cycle-time analysis (the SRE-style flow-efficiency metric) drops out trivially.

Measure types from the source:

| Type | Description | Example |
|---|---|---|
| Additive | Can be summed across all dimensions | Total PRs merged, total agent tokens used |
| Semi-additive | Can be summed across some dimensions but not time | Open issue count (snapshot at time T) |
| Non-additive | Cannot be summed meaningfully | Merge rate (ratio); calculate from additives |

Calculated non-additive metrics should not be stored — compute them at query time from their additive components. This is Muda elimination in the warehouse: don't precompute what you can derive.

## Data Vault when you're operating a fleet

When you operate one project, dimensional modeling is enough. When you operate a fleet — many agents, many repos, many providers, many users — Data Vault 2.0 (`data-modeling.md`) becomes the natural shape.

The Data Vault primitives:

- **Hub** — a list of unique business keys for a core entity. Hub on `agent_id`, hub on `repo_id`, hub on `issue_id`, hub on `user_id`, hub on `provider_id`.
- **Link** — a many-to-many relationship between hubs. Link `(agent_id, issue_id)`, link `(issue_id, user_id, role)`, link `(repo_id, provider_id)`.
- **Satellite** — descriptive attributes for a hub or link, with effective dates for SCD2 history. Satellite for `agent` (model, prompt template, tool surface). Satellite for `issue` (title, body / exec plan, current marker label).

Hash keys (MD5, SHA1) generate fixed-length surrogates for joins:

```sql
SELECT MD5(issue_id::VARCHAR) AS issue_skey FROM src_issue;
SELECT SHA1_BINARY(
    COALESCE(repo_id::VARCHAR,'') || '|' ||
    COALESCE(provider_id::VARCHAR,'')
) AS repo_provider_link_skey FROM src_repo_provider;
```

Diff hash detects changes without comparing every column:

```sql
SELECT MD5(
    COALESCE(title,'') || '|' ||
    COALESCE(body,'') || '|' ||
    COALESCE(current_marker,'')
) AS issue_diff_hash FROM src_issue;
```

The shape of the warehouse you'd build to *measure* fleet operations is literally a Data Vault. The hubs are the entities, the links are the relationships, the satellites are the SCD2 history.

## Streams + tasks + dynamic tables — real-time agent telemetry

Agent telemetry is a stream:

- Every tick → row to `fact_agent_session`.
- Every PR open/close → row to `fact_pr_outcome`.
- Every marker change → row to `fact_marker_transition`.

Snowflake **streams + tasks** is the natural shape (Iceberg + Flink + Trino is the same shape on a different stack):

```sql
CREATE STREAM strm_agent_sessions ON TABLE raw_agent_events;

CREATE TASK tsk_load_fact_session
    WAREHOUSE = transform_wh
    SCHEDULE = '5 MINUTE'
    WHEN SYSTEM$STREAM_HAS_DATA('strm_agent_sessions')
AS
    INSERT INTO fact_agent_session
    SELECT … FROM strm_agent_sessions WHERE METADATA$ACTION = 'INSERT';
```

The lakehouse pattern (bronze raw → silver cleaned → gold dimensional) gives the layers needed to keep raw audit history while serving fast dashboard queries.

Dynamic tables collapse the stream + task into one declarative object — define the target as a SQL query against the source, set a TARGET_LAG, Snowflake decides when to refresh. The agent-ops version: define `fact_marker_transition` as a SQL query against the raw event log; let Snowflake keep it fresh.

The point: **don't treat agent metrics as logs. Treat them as a data product.** The same dimensional rigour you'd apply to revenue analytics applies to agent throughput analytics.

---

# Part VII — Platform engineering for agent fleets

The `devops-and-platform-engineering.md` source covers 25+ books across Kubernetes, GitOps, CI/CD, platform-engineering practice, container security, and SRE. The patterns map directly onto **how to operate agent infrastructure at fleet scale**.

## Internal Developer Platform (IDP) for agent operators

When more than one team in the organisation runs agents, the same problems platform engineering solved for application teams resurface:

- **Golden paths** — opinionated, supported defaults so a new team can stand up an agent worker without 40 hours of yak-shaving. The `relay-worker` binary is the golden path: one config file, one systemd unit, one knowledge pack injection. Compare to "everyone rolls their own bash-script-around-codex" — same chaos as pre-platform application deployment.
- **Self-service provisioning** — a team should request "an agent for this repo with these markers" and get one back in minutes, not file a ticket and wait. A `relay-bootstrap` flow that scaffolds the marker labels, the harness-lock workflow, the systemd unit, and the inject command is the IDP shape applied here.
- **Paved roads, not walled gardens** — let teams off the golden path when they need to, but make the golden path obviously easier. A team can swap the agent endpoint, bring their own knowledge pack, write their own SKILL.md — but the default works out of the box.

## Golden paths

A golden path for an agent-operating team:

1. Run `relay-bootstrap init --provider github --repo owner/name`.
2. The wizard creates the marker labels in the GitHub repo.
3. The wizard installs the harness-lock workflow + branch protection.
4. The wizard generates the systemd unit + timer (and, optionally, the GitHub Actions workflow alternative).
5. The wizard scaffolds the first issue with an exec-plan template body and the `ready-for-agent` label.
6. The team gets a single-page "what to do next" with three commands.

Every step beyond that is the team's choice; this is the supported floor.

## GitOps for agent configuration

Agent configurations are themselves under version control. The GitOps idea — declarative state in git, a controller that converges live state to it — applies:

- The set of issues labelled `ready-for-agent` is the desired-state declaration ("I want these slices shipped").
- The PR queue is the converged state.
- The worker is the controller.
- Drift (an issue stuck in `agent-working` for 6 hours with no commits) is a reconciliation failure that should alert.

Argo CD's "sync wave" concept maps to dependency ordering between issues — one issue is `blocked-by` another via an issue link; the worker should respect that ordering.

## SRE-style error budgets

Two metrics that matter:

- **Agent SLO**: percentage of issues shipped without `blocked-on-human` intervention. If your target is 80% and you're at 60%, the error budget is exhausted and the team's next priority is investigating *why* the agent is asking for help so often.
- **Reviewer SLO**: percentage of agent PRs reviewed within 24h. If reviewers are the bottleneck, the agent is producing faster than the team can absorb — heijunka violation.

Error budgets reframe "the agent failed" from a binary to a budget. You can spend the budget on risky experiments (lower the agent's confidence threshold, try a cheaper model) and stop when you've used it up.

## Kubernetes-style runtime constraints

The **resource requests / limits / quotas** discipline from Kubernetes maps directly to agent runtime constraints:

| K8s primitive | Agent equivalent |
|---|---|
| `resources.requests.cpu` | Minimum guaranteed agent budget per tick |
| `resources.limits.cpu` | Hard cap on agent budget per tick (the `--agent-timeout`) |
| `LimitRange` | Per-team default for agent budget |
| `ResourceQuota` | Per-team total agent budget cap |
| `NetworkPolicy` | Tool capability surface — what the agent can reach |
| `PodSecurityPolicy` | Sandbox constraints (the relay math sandbox: no fs / network / process) |
| `livenessProbe` | Worker tick — if the agent is unresponsive, restart |
| `readinessProbe` | The marker check — only `ready-for-agent` issues are eligible |

You don't have to run agents on Kubernetes to use these as a design vocabulary. The constraints are the same shape regardless of the orchestrator.

## Observability for agent fleets

The minimum from the SRE / observability side of the platform-engineering corpus:

- **Structured logs** at every layer. Agent emits, worker emits, dispatcher emits. Correlate by trace ID.
- **Metrics**: `agent_session_duration_seconds`, `marker_transition_total`, `tool_call_total{tool=…}`, `model_token_usage_total{tier=low/med/high}`, `blocked_on_human_duration_seconds`. Histograms not just counters — the long tail matters.
- **Traces**: one trace per agent session, with spans for each tool call, each sub-LM dispatch, each PR operation.
- **Profiles**: continuous profiling catches the case where an agent is wedged on a regex backtrack rather than actually doing work.

Andon at the fleet level is a dashboard — but only useful if every agent's emitted telemetry is consistent. Standardised work for telemetry is a precondition.

## Identity-native infrastructure access for agents

The `devops-and-platform-engineering.md` Identity-Native Infrastructure Access Management material applies directly:

- **No long-lived secrets in the agent's environment.** Use short-lived OIDC tokens issued at session start; the agent presents the token to downstream services.
- **Workload identity, not API keys.** The agent's identity is its session; permissions are bound to that identity, not to a key file.
- **Audit every privileged action.** Every `merge_pr`, every `apply` against a cluster, every secret-fetch logged with the agent's identity.

For the unattended worker specifically: the agent runs on a VM with an IAM role; it never has root credentials in its environment; rotation is automatic. This converts the "agents will print environment variables if they can" attack surface into a non-issue.

---

# Part VIII — Anti-patterns: cargo-cult Lean

Borrowing Japanese manufacturing principles superficially is worse than not borrowing them. A few failure modes:

### "We do Kaizen" — but no measurement

If you have no eval harness, no metrics, no facts, then "continuous improvement" is just movement, not progress. Kaizen requires genjitsu. Without it you're holding meetings, not improving.

### "We have an Andon" — but nobody watches it

A Slack channel called `#agent-blocked` that nobody is paged on is not andon. Andon **routes to the actor who can fix it**, with a latency low enough that the line doesn't sit idle. If your agent can sit blocked overnight, your andon is broken.

### "We use Standardised Work" — but the standard is a wiki page nobody reads

Standardised work in TPS is the *thing the operator is doing right now*, posted at the workstation, in their hands. The exec plan in the issue body is standardised work. A SKILL.md the agent loads at session start is standardised work. A `docs/HOW-WE-RUN-AGENTS.md` that nobody opens is decoration.

### "We have Poka-yoke" — but it's a checklist

A checklist is not mistake-proofing; it's a *reminder*. Poka-yoke is mechanical: the harness lock CI **rejects** the diff, it does not just remind the agent. Branch protection **prevents** the merge. CODEOWNERS **enforces** review. If the device only "alerts" or "warns," it is not poka-yoke and the agent will eventually skip past it.

### "We do JIT" — but the queue is hidden

If `ready-for-agent` issues pile up because no agent is consuming them, you don't have JIT — you have a stockroom. JIT requires a pull signal that propagates upstream. The worker's `ListReady` is the pull signal; if your queue keeps growing and your worker keeps idle, the pull signal is broken.

### Mistaking "Lean" for "no slack"

Toyota's lean is about *eliminating waste*, not *eliminating slack*. An agent that has zero spare capacity will fail the moment one issue blocks. Heijunka requires capacity to absorb the inevitable lumps; Muri avoidance requires not loading the agent to its absolute maximum. "Run hot" is a TPS anti-pattern, not the goal.

### Cargo-culting vocabulary without the practice

Calling the issue label `andon-cord` doesn't make it andon. The practice — automatic, immediate, routed to the right actor, mechanical pause until resolved — is what matters. Use the Japanese terms when they capture something specific; drop them when they're decoration.

### Treating each principle in isolation

Jidoka without andon is mute. Andon without poka-yoke is noise. Poka-yoke without standardised work is arbitrary. Standardised work without kaizen is fossilised. Kaizen without genjitsu is wishful thinking. The principles are a system; isolated they stop working. The composite operating model in Part III is what holds them together.

---

# Part IX — Adoption playbook

Six steps to get from zero to a working Honda Construct agent operating model in a single team. Each step is one to three days of work.

### Step 1 — Establish the genba

Pick one Linux VM (or container) that is *not* the developer's laptop. Production-similar enough to deploy from. Doppler / Vault for secrets with a rotation policy. Install the agent CLI of choice (codex, claude code, relay terminal). Confirm the agent can run end-to-end manually before automating anything.

### Step 2 — Establish the standardised work

Pick one repo as pilot. Write the exec plan template (the seven fields). Write the SKILL.md for whatever workflow the agent will run. Decide the marker convention (default: `ready-for-agent`, `agent-working`, `blocked-on-human`, `stop`). Apply branch protection, enable auto-merge.

### Step 3 — Install the poka-yoke

Add the harness-lock CI workflow (rejects PRs that touch test runners / lint configs / workflow files unless the author is on the human allow-list). Add CODEOWNERS for sensitive paths. Tighten branch protection: require status checks, require linear history, disable force-push.

### Step 4 — Wire the OS layer

Either:

- systemd timer + worker shell script (for a single-machine setup), or
- `relay-worker --schedule "@every 5m"` (for the binary-orchestrated path), or
- A GitHub Actions workflow on `schedule: cron` (for a SaaS-only setup, accepting the 5-minute cron floor)

Confirm the worker exits cleanly with `ErrNoReadyItems` when the queue is empty; confirm it picks up the first `ready-for-agent` issue when one appears.

### Step 5 — Light the andon

Forward `journalctl -u relay-worker` (or the equivalent log) to your existing log aggregator. Add a metric for `blocked_on_human_count` and alert on `>0` for more than the SLO duration. Make sure the agent's PR comments tag `@reviewer` so the andon routes to a human, not a void.

### Step 6 — Begin Kaizen

Start with `MaxItemsPerTick = 1`. Run for a week. Hold a hansei session: what stopped the agent? What did the human have to fix? What was Muda? Update the exec plan template, the SKILL.md, the CI rules. Iterate. This is the actual work — the previous five steps were just installing the substrate.

After a quarter of weekly hansei + measured kaizen, you will have an agent operation that is more disciplined than most human teams. That is the bar.

---

# Part X — Reference implementation in the local codebases

Catalog of which artifacts in the local codebases implement which principles. Use this as a directory when you want to see the pattern in code.

| Principle | Where to look |
|---|---|
| Jidoka — agent stops on detected defect | `relay-worker.processItem` (calls `Block` on agent error or `OutcomeBlocked`); harness-lock CI workflow |
| Jidoka — agent refuses out-of-scope verbs | `internal/worker/github/github.go::SetWorking` returns false when label already set; `verb_not_allowed` patterns in github-ops, jira-ops, linear-ops, azdo-ops agents |
| Jidoka — token-stream defects | `relay/internal/construct/muda.go::MudaStripper` |
| Andon — marker labels | `worker.WorkSource` interface methods `Block`, `Resume`, `MarkDone`, `SetWorking`, `ClearWorking` |
| Andon — issue comments | `worker.WorkSource.Comment` |
| Andon — structured logs | `internal/logging` (relay), `slog`-based structured logging across all packages |
| Andon — PR status checks | GitHub Actions workflows; branch protection settings |
| Andon — live canvas | agent-orchestration cookbook `dag-task-runner` |
| JIT and Pull — worker queue | `relay-worker.tickOnce` only acts when `ListReady` returns items |
| JIT — RLM corpus retrieval | `rlm-context-agent` `search_contexts.py` returns top-K chunks per query, not the whole corpus |
| Heijunka — `MaxItemsPerTick` | `worker.Args.MaxItemsPerTick`; defaulted to 1 |
| Heijunka — complexity tiers | `rlm-subcall-{low,med,high}` agents; DAG runner `complexity` field |
| Heijunka — DAG rank parallelism | agent-orchestration cookbook `dag-task-runner.computeRanks` (Kahn's algorithm) |
| Kaizen — eval harness | `relay-eval`; `ai-agents.md` Self-Improving Agent pattern |
| Kaizen — thin slices | exec plan template (one slice per session) |
| Poka-yoke — harness lock | `harness-lock.yml` workflow (per-repo); CODEOWNERS rules |
| Poka-yoke — tarball verification | `rlm-context-agent.installer.packs.unpack_into_cache` (path-traversal guard); `download_pack` (sha256) |
| Poka-yoke — tool sandbox | `relay/internal/tools/math.go` (no fs/network/process) |
| Poka-yoke — sensitive-data guard | `relay/internal/construct/muda.go::IsSensitive` strips paths like `.har` and `.env` from output |
| Muda — book extraction | `extract_per_book.py` (93% retention; strips boilerplate) |
| Muda — PR comment triage | `/pr-review-triage` skill (categorise every comment; refuse to silently ignore) |
| 5S — gitignore discipline | rlm-context-agent PR #23 (gitignore self-install + worktree dirs); relay's `.gitignore` |
| 5S — repo conventions | `cmd/<binary>/`, `internal/<package>/` layout in relay; `assets/{agents,commands,skills}/` in rlm-context-agent |
| Standardised work — exec plan | the seven fields (milestone, slice, proving test, lint, expected red, files in scope, validation evidence) — issue body convention |
| Standardised work — SKILL.md files | `assets/skills/<name>/SKILL.md` in rlm-context-agent (rlm, work, library, pr-review-triage, large-text, books) |
| Standardised work — sub-agent contracts | `assets/agents/<name>.md` files (rlm-subcall, github-ops, pr-reviewer, books-subcall, etc.) |
| SMED — pack cache | `~/.rlm_cache/packs/<name>/<version>/`; `rlm-context-agent.packs.list_cached`, `remove_cached` |
| SMED — idempotent installers | `installer.inject` (cache-skip); `extract_per_book.py` (mtime-skip); `relay-worker` (marker-skip) |
| Genchi Genbutsu — RLM | the entire `rlm-context-agent` codebase |
| Genchi Genbutsu — provenance | `ai-agents.md` Knowledge Retrieval Agent's "Provenance component" |
| Hansei — PR review skill | `assets/skills/pr-review-triage/SKILL.md` |
| Hansei — security review skill | `assets/skills/security-review/SKILL.md` (when present); `claude-code` `/security-review` slash command |

---

## Glossary

| Term | Source | Meaning |
|---|---|---|
| **Andon** | TPS | Visible signal of trouble that routes to whoever can fix it |
| **Genba** | Honda / TPS | The actual workplace where the work happens |
| **Genbutsu** | Honda / TPS | The actual thing being worked on |
| **Genchi Genbutsu** | TPS | Go to the source; trust your own observation over reports |
| **Genjitsu** | Honda | The actual facts; numbers not vibes |
| **Hansei** | TPS / Zen | Honest reflection on what happened, including successes |
| **Heijunka** | TPS | Level the workload to smooth out peaks and valleys |
| **Honda Construct** | local (relay) | The local vocabulary for TPS-inspired agentic principles |
| **Jidoka** | TPS | Autonomation — automation with the authority to stop the line |
| **JIT** | TPS | Just-in-time pull-based production |
| **Kaizen** | TPS | Small, continuous improvement |
| **Muda / Mura / Muri** | TPS | Waste / unevenness / overburden |
| **Poka-yoke** | TPS | Mistake-proofing — make defects impossible or immediately obvious |
| **Sangen Shugi** | Honda | The three reals: genba, genbutsu, genjitsu |
| **SMED** | TPS | Single-minute exchange of die — rapid changeover |
| **Standardised work** | TPS | The best-known method, documented and followed until improved |
| **Three Joys** | Honda | Joy of buying, selling, creating — the philosophy of who the work is for |
| **Wai-Gaya** | Honda | Flat-hierarchy structured argument until consensus |
| **5S** | TPS | Sort, set in order, shine, standardise, sustain |
| **ADL** | AI agents | Agent Development Lifecycle — six-phase methodology |
| **Andon (agent)** | this doc | Marker file / label / comment / log signalling agent-loop trouble |
| **BKT** | AI agents | Bayesian Knowledge Tracing — student-mastery estimation |
| **Brier score** | AI agents | Proper scoring rule for confidence calibration |
| **Conformed dimension** | Kimball | Shared dimension reused across fact tables for joinable analysis |
| **Data Vault** | Linstedt | Hub / link / satellite warehouse model for fleet-scale state |
| **Exec plan** | unattended-agent doc | Issue body containing milestone, next slice, proving test, etc. |
| **Grain** | Kimball | The atomic unit a fact table represents |
| **Harness lock** | unattended-agent doc | CI rule rejecting agent diffs to harness files |
| **IRT** | AI agents | Item Response Theory — adaptive assessment |
| **Marker file / label** | unattended-agent doc | The control plane primitive: `ready-for-agent`, `agent-working`, `blocked-on-human`, `stop` |
| **Pack** | rlm-context-agent | Versioned tarball of static knowledge + vector index |
| **Platt scaling** | AI agents | Sigmoid-based confidence calibration |
| **POMDP** | AI agents | Partially observable Markov decision process |
| **PTCF** | AI agents | Persona, Task, Context, Format — prompt blueprint |
| **ReAct** | AI agents | Reason → Act → Observe loop pattern |
| **RLM** | rlm-context-agent | Recursive Language Model — externalised corpus + sub-LM per chunk |
| **SCD2** | Kimball | Slowly-changing dimension Type 2 — full history with effective dates |
| **Slice** | unattended-agent doc | One thin unit of agent work — small enough to test, small enough to merge |
| **SKILL.md** | rlm-context-agent | Markdown playbook codifying a workflow for an agent to follow |
| **TDG** | AI agents | Test-Driven Generation — TDD adapted for LLM code generation |
| **WorkSource** | relay-worker | Provider-agnostic interface over GitHub / Jira / GitLab / Trello |

---

## References to the source corpus

This document synthesises across:

- [`unattended-agent-architecture.md`](./unattended-agent-architecture.md) — three-layer architecture, marker convention, harness lock, the worked token-expired example. The empirical foundation for the whole synthesis.
- [`ai-agents.md`](./ai-agents.md) — agent fundamentals, ReAct, plan-and-execute, multi-agent supervisor, memory hierarchies, tool-selection funnel, evaluation and continuous improvement, ethics and refusal patterns, healthcare/legal/financial/education/scientific domain agents, embodied agents and the asymmetric control loop.
- [`agent-orchestration.md`](./agent-orchestration.md) — five Cursor SDK cookbook patterns; headless agents; the DAG runner with rank parallelism (heijunka of compute); cycle detection (DFS tri-color); Kahn's-algorithm topological ranking; live-canvas hot-reload (andon); cross-platform mappings (Cursor SDK ↔ Claude Agent SDK ↔ OpenAI Assistants).
- [`data-modeling.md`](./data-modeling.md) — conceptual / logical / physical / transformational model types; Snowflake architecture (storage, compute, services); micro-partitions and clustering; table types (permanent / transient / temporary / external / iceberg / hybrid); streams + tasks + dynamic tables; constraints and keys; semi-structured VARIANT data; database normalisation 1NF–6NF; Kimball dimensional modeling (bus matrix, conformed dimensions, role-playing, junk, outrigger); Slowly-Changing Dimensions Types 0–6; fact-table patterns; Data Vault 2.0 (hubs, links, satellites, hash keys, diff hash); Data Mesh and Data Lakehouse.
- [`devops-and-platform-engineering.md`](./devops-and-platform-engineering.md) — IDP / golden paths; GitOps; Argo CD sync waves; SRE error budgets; Kubernetes resource constraints; observability practice (USE / RED metrics, structured logs, traces, profiles); identity-native infrastructure access; container security; CI/CD design patterns. Material drawn across 25+ books in the source.
- relay codebase — `internal/construct/` (the local Honda Construct vocabulary), `cmd/relay-worker/`, `internal/worker/` (the unattended-agent architecture realised as a Go binary).
- rlm-context-agent codebase — knowledge-pack inject machinery, RLM sub-call complexity tiers, the books skill, the pr-review-triage skill, the work-graph control plane.

The recursive language model paper, the Cursor SDK cookbook, and Geoffrey Huntley's Ralph technique are the named external references underlying the corpus.

---

## Closing

The argument of this document, stated again:

> **Treat your AI agent operation as a Toyota assembly line, not as a smarter programmer.**

Everything else — the marker conventions, the harness lock, the eval harness, the IDP, the data marts, the knowledge packs, the multi-agent debate engines, the calibrated-confidence escalation — is implementation of that one stance.

Toyota's principles are old enough that they have been argued through, refined, cargo-culted, and rediscovered many times. Adopting them whole and applying them to agent ops is not the radical move it might first seem — it is the conservative one. The radical move is *not* to adopt them and hope your agent is good enough that none of it matters.

It will not be. Not yet. Maybe not for a long time.

Run the line. Stop the line when something is wrong. Improve the standard. Ship the next slice. That is the work.
