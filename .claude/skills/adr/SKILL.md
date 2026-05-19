---
name: new-adr
description: Create a new Architecture Decision Record. Use when documenting technical decisions, choosing between technologies, defining patterns, or recording architectural choices.
argument-hint: "[title]"
allowed-tools: Read, Glob, Write, Bash, AskUserQuestion, Skill
---

# Create Architecture Decision Record

Create a new ADR in the `ADRs/` folder following the project template and conventions.

## Process

### Step 1: Refresh the PR stack

Ask the user if they want to refresh the PR stack first so all branches are up to date. If yes, run the `/refresh-pr-stack` skill before continuing.

### Step 2: Determine the next ADR number

Check existing ADRs (in the top-of-stack branch) and open draft PRs to determine the next available number. This prevents number conflicts.

```
# Check existing files on the top branch
ls ADRs/
# Check open PRs for reserved numbers
gh pr list --state open --json title --jq '.[].title'
```

### Step 3: Reserve the ADR number immediately

Create the branch on top of the current stack, write a placeholder ADR, push it, and create a draft PR.

1. **Find the top of the stack** — the branch of the highest-numbered open ADR PR:
   ```
   gh pr list --state open --json number,headRefName --jq 'sort_by(.number) | last | .headRefName'
   ```
   If no open PRs, use `main`.

2. **Branch from the top of the stack**:
   ```
   git fetch origin
   git checkout origin/<top-branch> -b adr-NNNN
   ```

3. **Create placeholder ADR** at `ADRs/NNNN-kebab-case-title.md`:
   ```yaml
   ---
   status: draft
   date: YYYY-MM-DD
   owner:
   superseded_by:
   tags: []
   ---
   # NNNN - Title

   > This ADR is being drafted. Content will follow.
   ```

4. **Commit, push, and create draft PR**:
   ```
   git add ADRs/NNNN-kebab-case-title.md
   git commit -m "docs: reserve adr-NNNN kebab-case-title"
   git push -u origin adr-NNNN
   gh pr create --draft --base <top-branch> --title "ADR-NNNN: Title" --body "ADR for <title>. Draft in progress."
   ```

### Step 4: Gather context from the user

Do NOT guess the ADR content from the title alone. Ask the user questions to gather accurate context before writing anything:

1. **What is the decision about?** — What problem or question does this ADR address?
2. **What are the constraints?** — Technical, business, timeline, or team constraints that shape the decision.
3. **What alternatives were considered?** — At least 2-3 options the user has in mind, with pros/cons for each.
4. **What is the preferred decision?** — Which option does the user lean towards and why?
5. **Who is the owner?** — Who is responsible for this ADR?

Adapt the questions to what the user already provided in their initial request. Don't ask for information they've already given. If the user provided a detailed brief, skip to confirmation.

### Step 5: Read existing documents for context

Before writing, read all existing ADRs and relevant documents (Architecture Proposal, High Level Design) in the current branch to:
- Ensure consistency with existing decisions
- Find ADRs to reference using `[[NNNN-title]]` links
- Align terminology and patterns with the rest of the project
- Avoid contradicting or duplicating existing content

### Step 6: Write the ADR

Replace the placeholder with the full ADR content. Keep the status as `draft` - the `/submit-adr` skill handles the transition to `proposed` when the ADR is ready for review.

**Frontmatter:**
```yaml
---
status: draft
date: YYYY-MM-DD (use today's date)
owner: (from step 4)
superseded_by:
tags: [relevant, tags]
---
```

**Content sections:**

#### Context
- State the problem or decision point clearly
- Include relevant constraints (technical, business, timeline)
- Mention what triggered this decision
- Reference related ADRs using `[[NNNN-title]]`

#### Decision
- State the decision clearly and concisely
- Explain the chosen approach with enough detail to be actionable
- Be specific: include versions, configurations, or patterns chosen
- Use tables, diagrams (Mermaid), and code examples where they add clarity

#### Alternatives considered
- List each alternative with pros and cons
- Explain why each was rejected in a constructive tone

#### Consequences
- List positive outcomes (benefits, improvements)
- List negative outcomes (trade-offs, costs, risks)
- Note what this enables or prevents in the future
- Mention any follow-up actions or related decisions needed

### Step 7: User review

Present the draft to the user and ask for feedback. Iterate until they're satisfied.

### Step 8: Commit and push the final content

1. **Commit**:
   ```
   git add ADRs/NNNN-kebab-case-title.md
   git commit -m "docs: add adr-NNNN kebab-case-title"
   git push
   ```

2. **Return the PR URL** to the user.

## Quality Checklist

Before finishing, verify:
- [ ] Title is clear and descriptive
- [ ] Date is set to today
- [ ] Tags are relevant and consistent with existing ADRs
- [ ] Context explains WHY this decision is needed
- [ ] Decision is specific and actionable
- [ ] Alternatives are listed with constructive rejection reasons
- [ ] Consequences cover both pros and cons
- [ ] References related ADRs where relevant
- [ ] Terminology is consistent with existing documents

## Template Reference

See [[ADRs/0000-template]] for the base template structure.