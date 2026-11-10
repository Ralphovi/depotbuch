#!/usr/bin/env bash
# Move cargo-deny's advisory database to the commit the .github/advisory-db submodule pins,
# so the gate audits a fixed database:
#
#   scripts/advisory-db.sh && cargo deny --offline check advisories
#
# A newly published advisory then reaches the gate only through Dependabot's daily PR that
# moves the pin, instead of turning every open PR red at once. Only the submodule's commit
# is read; nothing checks the submodule out. deny.toml keeps the database in
# target/advisory-dbs (db-path), so this never rewinds the shared copy in $CARGO_HOME.
#
# It also runs `cargo fetch --locked`, because --offline stops cargo-deny downloading
# crates too. To audit against the newest database instead, run plain
# `cargo deny check advisories`: .github/workflows/advisories.yml does that daily, and a
# release should do it before building.
set -euo pipefail
die() { echo "advisory-db: $*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"
entry="$(git ls-files -s -- .github/advisory-db)"
read -r mode pin _ <<<"$entry" || true
[ "${mode:-}" = 160000 ] && [[ "${pin:-}" =~ ^[0-9a-f]{40}$ ]] \
  || die ".github/advisory-db is not a submodule gitlink in the index (got '$entry')"

find_db() {
  [ -d target/advisory-dbs ] || return 0
  find target/advisory-dbs -mindepth 1 -maxdepth 1 -type d -name 'advisory-db-*' | head -1
}
# cargo-deny names its clone after a hash of the database URL, so let it create the clone.
db="$(find_db)"
if [ -z "$db" ]; then
  cargo deny fetch db
  db="$(find_db)"
  [ -n "$db" ] || die "cargo deny fetch db left no advisory-db-* clone in target/advisory-dbs"
fi
if [ "$(git -C "$db" rev-parse HEAD)" != "$pin" ]; then
  git -C "$db" fetch --quiet --depth 1 origin "$pin"
  git -C "$db" checkout --quiet --detach "$pin"
fi
# cargo-deny's maximum-db-staleness dates the database by its last fetch, which the fetch
# above refreshes on every fresh checkout, so check the pinned commit's own date.
max_days="${ADVISORY_DB_MAX_AGE_DAYS:-90}"
age_days=$(( ($(date +%s) - $(git -C "$db" log -1 --format=%ct HEAD)) / 86400 ))
[ "$age_days" -le "$max_days" ] || die "the pinned advisory database is $age_days days old \
(limit $max_days); merge Dependabot's PR that moves .github/advisory-db"
echo "advisory database pinned at $pin"
cargo fetch --locked
