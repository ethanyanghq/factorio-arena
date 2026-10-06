#!/usr/bin/env sh
# pre-push guard: refuse pushes that target main on any remote.
# GitHub branch protection is unavailable on this private Free-plan repo,
# so this is the local substitute. Bypass deliberately with `git push --no-verify`.
case "$PRE_COMMIT_REMOTE_BRANCH" in
  refs/heads/main)
    echo "refusing to push to main; open a pull request (or use --no-verify)" >&2
    exit 1
    ;;
esac
