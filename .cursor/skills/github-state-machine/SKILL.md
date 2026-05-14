---
name: github-state-machine
description: >-
  GitHub Issues as Catalyst's durable state machine: label vocabulary (state/,
  type/, severity/, verdict/, modifier labels), legal transitions, ownership
  semantics, audit comments, webhook event routing, and the Catalyst Andon
  project board. Use when implementing state transitions, webhook handlers,
  or debugging illegal-transition errors.
---
<!-- Vendored from: platform-catalyst/.cursor/skills/github-state-machine/SKILL.md (BittahCriminal/platform-catalyst, BSD-3-Clause). Adapted for Catalyst: PLAN.md/CLAUDE.md/DECISIONS.md scrubbed; ADR-008->ADR-001, ADR-009->ADR-002. -->


# GitHub state machine

## Role

You guide implementation of the GitHub Issues state machine that is the durable substrate for all Catalyst automations. Every deploy, PR review, secret rotation, preview environment, and ops-intel finding is a GitHub Issue with labels encoding state, comments providing audit trail, and the "Catalyst Andon" project board providing visibility. You enforce the spec in `docs/STATE-MACHINE.md` and the decision in ADR-001.

For **how to execute work against an Issue** (Gherkin AC, test mapping, docs checklist, dependency on-hold without illegal transitions), use **`@issue-execution-gherkin-workflow`**.

## Instructions

### 1. The five-property substrate

Every Catalyst automation MUST satisfy all five (from `docs/STATE-MACHINE.md` §1):

| Property | Implementation |
|----------|---------------|
| **Persistent state** | Issue body + labels |
| **Defined state machine** | `state/*` label set with legal transitions |
| **Ownership** | Issue `assignees` field |
| **Defined verbs** | `create`, `comment`, `assign`, `label`, `close` |
| **Audit history** | Issue timeline + structured comments |

### 2. Label vocabulary (from `docs/STATE-MACHINE.md` §2)

**State labels** (exclusive — exactly one):

| Label | Meaning | Initial? | Terminal? |
|-------|---------|:--------:|:--------:|
| `state/pending` | Created, not yet picked up | yes | |
| `state/agent-working` | Agent actively processing | | |
| `state/blocked-on-human` | Needs human decision | | |
| `state/done` | Completed successfully | | yes |
| `state/rolled-back` | Failed, rollback applied | | yes |
| `state/cancelled` | User-cancelled | | yes |

**Type labels** (exclusive): `type/deploy`, `type/secret-rotation`, `type/preview-env`, `type/pr-review`, `type/ops-intel-finding`, `type/ops-intel-digest`, `type/incident`

**Construct address labels** (mandatory, from ADR-002): `tenant/*`, `env/*`, `lz/*`, `project/*`, `app/*`

**Additive labels**: deploy subtypes, severity, verdict, modifiers — see `docs/STATE-MACHINE.md` §2.3-2.6.

### 3. Legal state transitions

```
state/pending → state/agent-working | state/cancelled
state/agent-working → state/done | state/blocked-on-human | state/rolled-back
state/blocked-on-human → state/agent-working | state/cancelled
state/done → (terminal)
state/rolled-back → (terminal)
state/cancelled → (terminal)
```

**Any other transition is illegal** and raises `IllegalTransitionError`.

### 4. State machine implementation

```python
# services/catalyst-api/catalyst/state_machine.py
from enum import StrEnum

class State(StrEnum):
    PENDING = "state/pending"
    AGENT_WORKING = "state/agent-working"
    BLOCKED_ON_HUMAN = "state/blocked-on-human"
    DONE = "state/done"
    ROLLED_BACK = "state/rolled-back"
    CANCELLED = "state/cancelled"

LEGAL_TRANSITIONS: dict[State, frozenset[State]] = {
    State.PENDING: frozenset({State.AGENT_WORKING, State.CANCELLED}),
    State.AGENT_WORKING: frozenset({State.DONE, State.BLOCKED_ON_HUMAN, State.ROLLED_BACK}),
    State.BLOCKED_ON_HUMAN: frozenset({State.AGENT_WORKING, State.CANCELLED}),
    State.DONE: frozenset(),
    State.ROLLED_BACK: frozenset(),
    State.CANCELLED: frozenset(),
}

TERMINAL_STATES = frozenset({State.DONE, State.ROLLED_BACK, State.CANCELLED})

class IllegalTransitionError(Exception):
    def __init__(self, from_state: State, to_state: State, issue_number: int):
        self.from_state = from_state
        self.to_state = to_state
        self.issue_number = issue_number
        super().__init__(
            f"Illegal transition: {from_state} → {to_state} on issue #{issue_number}"
        )

def validate_transition(from_state: State, to_state: State, issue_number: int) -> None:
    if to_state not in LEGAL_TRANSITIONS[from_state]:
        raise IllegalTransitionError(from_state, to_state, issue_number)
```

### 5. Transition execution (GitHub API calls)

```python
async def transition_issue(
    github: GitHubClient,
    repo: str,
    issue_number: int,
    from_state: State,
    to_state: State,
    summary: str,
    run_id: str,
    trace_id: str,
) -> None:
    """Execute a state transition with audit comment."""
    # 1. Read fresh state (eventual consistency)
    current_labels = await github.get_issue_labels(repo, issue_number)
    current_state = extract_state(current_labels)
    if current_state != from_state:
        raise IllegalTransitionError(current_state, to_state, issue_number)

    # 2. Validate transition
    validate_transition(from_state, to_state, issue_number)

    # 3. Update labels atomically
    new_labels = [l for l in current_labels if not l.startswith("state/")] + [to_state]
    await github.set_issue_labels(repo, issue_number, new_labels)

    # 4. Update assignees per ownership semantics
    await update_assignees(github, repo, issue_number, to_state)

    # 5. Post audit comment (mandatory)
    comment = format_audit_comment(from_state, to_state, summary, run_id, trace_id)
    await github.create_issue_comment(repo, issue_number, comment)

    # 6. Close if terminal
    if to_state in TERMINAL_STATES:
        state_reason = "completed" if to_state != State.ROLLED_BACK else "not_planned"
        await github.close_issue(repo, issue_number, state_reason)
```

### 6. Audit comment format

```markdown
## Catalyst -- {transition_name}

**From state**: `{from_state}`
**To state**: `{to_state}`
**Actor**: catalyst-bot[bot]
**Run ID**: {run_id}
**Trace ID**: {trace_id}
**Duration**: {duration}s
**Summary**: {summary}
```

Every state transition MUST be paired with a comment. No silent transitions.

### 7. Ownership semantics

| State | Assignee MUST be |
|-------|-----------------|
| `state/pending` | Unassigned or the human requester |
| `state/agent-working` | `catalyst-bot[bot]` only |
| `state/blocked-on-human` | Human(s) — original requester + SME |
| Terminal states | Unchanged from prior |

### 8. Webhook event routing

The `webhook-handler` Lambda receives GitHub webhook events and routes them:

```python
EVENT_ROUTES: dict[str, Callable] = {
    "pull_request.opened": handle_pr_opened,
    "pull_request.synchronize": handle_pr_updated,
    "issues.labeled": handle_issue_labeled,
    "issue_comment.created": handle_issue_comment,
}

async def route_webhook(event_type: str, action: str, payload: dict) -> None:
    key = f"{event_type}.{action}"
    handler = EVENT_ROUTES.get(key)
    if handler:
        await handler(payload)
    else:
        logger.debug("unhandled_webhook", event_type=event_type, action=action)
```

### 9. Dependency validation

Before `state/pending → state/agent-working`, check `Depends on #N` references:

```python
async def check_dependencies(github, repo, issue_number) -> list[int]:
    """Return list of blocking issue numbers that are not yet done."""
    body = await github.get_issue_body(repo, issue_number)
    deps = re.findall(r"Depends on #(\d+)", body)
    blockers = []
    for dep_num in deps:
        dep_state = await github.get_issue_state_label(repo, int(dep_num))
        if dep_state != State.DONE:
            blockers.append(int(dep_num))
    return blockers
```

### 10. Eventual consistency rules

- Read fresh state from GitHub at every decision boundary.
- DDB cache is read-through, never write-through.
- On illegal-transition error: **stop, log, comment** — never retry-with-force.
- The illegal transition is a hansei trigger (post-mortem candidate).

## Output

- **State machine module**: `State` enum + `LEGAL_TRANSITIONS` + validation + transition execution
- **Webhook router**: event routing table + handler stubs
- **Audit comment**: template + formatter
- **Test**: transition validation tests (legal and illegal)

## Guardrails

- The legal-transition table in code MUST match `docs/STATE-MACHINE.md` exactly.
- No transitions outside the five defined verbs (`create`, `comment`, `assign`, `label`, `close`).
- No re-opening terminal-state Issues — open a new Issue and reference the old one.
- Changes to the label vocabulary require updating: this code, `STATE-MACHINE.md`, the Terraform label module, and a **`type/kaizen`** Issue (or `KAIZEN.md` archive pointer) documenting the vocabulary change.
- A CI policy (`policy/opa/state_machine.rego`) asserts these stay in sync.
