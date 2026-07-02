#!/usr/bin/env bash
# sync-upstream.sh — Sync this Lookin-AI fork with its AgriciDaniel upstream,
# ALWAYS via a review Pull Request, NEVER a direct push to the protected `main`.
#
# Behaviour (decision seo-D-8):
#   - no new upstream commits            -> prints "già aggiornato", exits 0, writes nothing
#   - clean merge of upstream/main       -> pushes a temp branch + opens a review PR
#   - conflicting merge                  -> aborts, lists conflicting files, writes nothing remotely, exits 1
#
# `main` is branch-protected (PR required): this script never runs `git push origin main`.
# The GitHub Action .github/workflows/upstream-sync.yml runs the same logic on a schedule.
set -euo pipefail

# --- files that ALWAYS conflict because this fork is rebranded to Lookin-AI (E-1) ---
# Listed in the PR body as "expected rebrand noise" so the reviewer can tell it
# apart from genuine functional upstream changes.
REBRAND_FILES=(
  "README.md" "CITATION.cff" ".claude-plugin/marketplace.json"
  ".claude-plugin/plugin.json" ".github/CODEOWNERS" ".github/FUNDING.yml"
)

# --- preconditions ---
command -v git >/dev/null || { echo "ERRORE: git non trovato." >&2; exit 2; }
command -v gh  >/dev/null || { echo "ERRORE: gh (GitHub CLI) non trovato." >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo "ERRORE: gh non autenticato. Esegui 'gh auth login'." >&2; exit 2; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERRORE: non sei in un repo git." >&2; exit 2; }
git remote get-url upstream >/dev/null 2>&1 || { echo "ERRORE: remote 'upstream' non configurato." >&2; exit 2; }

SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner)   # es. Lookin-AI/claude-seo
BRANCH="upstream-sync-$(date +%Y-%m-%d)"

echo "→ Fetch di origin e upstream…"
git fetch --quiet origin main
git fetch --quiet upstream main

NEW_COMMITS=$(git log origin/main..upstream/main --oneline)
if [ -z "$NEW_COMMITS" ]; then
  echo "già aggiornato — nessun nuovo commit su upstream/main."
  exit 0
fi

# idempotency: se una PR di sync per oggi esiste già, non ricrearla
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
  echo "Il branch $BRANCH esiste già su origin — verifica la PR aperta invece di ricrearla."
  exit 0
fi

echo "→ Nuovi commit da upstream/main:"
echo "$NEW_COMMITS"

# lavoriamo su un branch temporaneo staccato da origin/main: main non viene MAI toccato
git switch --quiet -c "$BRANCH" origin/main

if git merge --no-edit upstream/main >/dev/null 2>&1; then
  # --- merge pulito: push del branch + apertura PR (mai push su main) ---
  git push --quiet -u origin "$BRANCH"
  BODY=$(printf 'Sync automatico da \`upstream/main\` (AgriciDaniel).\n\n### Commit integrati\n%s\n' "$NEW_COMMITS")
  gh pr create --repo "$SLUG" --base main --head "$BRANCH" \
    --title "Upstream sync $BRANCH" \
    --body "$BODY" \
    --label "upstream-sync" >/dev/null
  echo "✓ Merge pulito. PR di revisione aperta verso main (nessun push diretto su main)."
  git switch --quiet -
else
  # --- conflitti: abort, nessuna scrittura remota, lista file ---
  CONFLICTS=$(git diff --name-only --diff-filter=U)
  git merge --abort
  git switch --quiet -
  git branch -D "$BRANCH" >/dev/null 2>&1 || true
  echo "⚠ CONFLITTI — nessuna modifica pubblicata. File in conflitto:"
  echo "$CONFLICTS"
  echo ""
  echo "(I file rebrand confliggono sempre ed è atteso: ${REBRAND_FILES[*]})"
  echo "Risolvi manualmente, poi riesegui, oppure usa la GitHub Action che apre comunque una PR di revisione."
  exit 1
fi
