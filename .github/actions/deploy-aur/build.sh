#!/bin/bash
# shellcheck disable=SC2024

set -o errexit -o pipefail -o nounset

pkgname=$INPUT_PKGNAME
pkgbuild=$INPUT_PKGBUILD
assets=$INPUT_ASSETS
updpkgsums=$INPUT_UPDPKGSUMS
test=$INPUT_TEST
read -r -a test_flags <<< "$INPUT_TEST_FLAGS"
post_process=$INPUT_POST_PROCESS
commit_username=$INPUT_COMMIT_USERNAME
commit_email=$INPUT_COMMIT_EMAIL
ssh_private_key=$INPUT_SSH_PRIVATE_KEY
commit_message=$INPUT_COMMIT_MESSAGE
allow_empty_commits=$INPUT_ALLOW_EMPTY_COMMITS
force_push=$INPUT_FORCE_PUSH
ssh_keyscan_types=$INPUT_SSH_KEYSCAN_TYPES
expected_revision_file=${INPUT_EXPECTED_REVISION_FILE:-}

assert_non_empty() {
  name=$1
  value=$2
  if [[ -z "$value" ]]; then
    echo "::error::Invalid Value: $name is empty." >&2
    exit 1
  fi
}

assert_non_empty inputs.pkgname "$pkgname"
assert_non_empty inputs.pkgbuild "$pkgbuild"
assert_non_empty inputs.commit_username "$commit_username"
assert_non_empty inputs.commit_email "$commit_email"
assert_non_empty inputs.ssh_private_key "$ssh_private_key"

export HOME=/home/builder

GLOBIGNORE=".:.."

echo '::group::Adding aur.archlinux.org to known hosts'
# Pins published at https://aur.archlinux.org/; rotation requires review.
host_keys=$(ssh-keyscan -t "$ssh_keyscan_types" aur.archlinux.org)
[[ -n "$host_keys" ]]
: > ~/.ssh/known_hosts
while IFS= read -r host_key; do
  fingerprint=$(printf '%s\n' "$host_key" | ssh-keygen -lf - -E sha256 | awk '{print $2}')
  case "$fingerprint" in
    SHA256:RFzBCUItH9LZS0cKB5UE6ceAYhBD5C8GeOBip8Z11+4|SHA256:uTa/0PndEgPZTf76e1DFqXKJEXKsn7m9ivhLQtzGOCI|SHA256:5s5cIyReIfNNVGRFdDbe3hdYiI5OelHGpw2rOUud3Q8)
      printf '%s\n' "$host_key" >> ~/.ssh/known_hosts ;;
    *) echo 'Unrecognized AUR SSH host fingerprint.' >&2; exit 1 ;;
  esac
done <<< "$host_keys"
echo '::endgroup::'

echo '::group::Importing private key'
echo "$ssh_private_key" >~/.ssh/aur
chmod -vR 600 ~/.ssh/aur*
ssh-keygen -vy -f ~/.ssh/aur >~/.ssh/aur.pub
echo '::endgroup::'

echo '::group::Checksums of SSH keys'
sha512sum ~/.ssh/aur ~/.ssh/aur.pub
echo '::endgroup::'

echo '::group::Configuring Git'
git config --global user.name "$commit_username"
git config --global user.email "$commit_email"
echo '::endgroup::'

echo '::group::Cloning AUR package into /tmp/local-repo'
# Authenticated AUR cloning supports empty repositories for first publication.
# Any clone failure is fatal: never infer package absence from a network error.
git clone -v "ssh://aur@aur.archlinux.org/${pkgname}.git" /tmp/local-repo
if ! git -C /tmp/local-repo rev-parse --verify HEAD >/dev/null 2>&1; then
  if [[ "$force_push" != false ]]; then
    echo 'First publication must not use force_push.' >&2
    exit 1
  fi
  git -C /tmp/local-repo checkout -B master
fi
if [[ -n "$expected_revision_file" ]]; then
  expected_revision=$(cat "$expected_revision_file")
  actual_revision=$(git -C /tmp/local-repo rev-parse --verify HEAD 2>/dev/null) || actual_revision=absent
  if [[ "$expected_revision" != "$actual_revision" ]]; then
    echo 'AUR changed after preparation; aborting without overwriting it.' >&2
    exit 1
  fi
fi
echo '::endgroup::'

echo '::group::Copying files into /tmp/local-repo'
{
  echo "Copying $pkgbuild"
  cp -r "$pkgbuild" /tmp/generated-PKGBUILD
  if [[ -f /tmp/local-repo/PKGBUILD ]]; then
    incoming_version=$(sed -n 's/^pkgver=//p' /tmp/generated-PKGBUILD)
    existing_version=$(sed -n 's/^pkgver=//p' /tmp/local-repo/PKGBUILD)
    incoming_rel=$(sed -n 's/^pkgrel=//p' /tmp/generated-PKGBUILD)
    existing_rel=$(sed -n 's/^pkgrel=//p' /tmp/local-repo/PKGBUILD)
    # Cloned values are data, not shell or sed programs. Never source them.
    for version in "$incoming_version" "$existing_version"; do
      [[ "$version" =~ ^[a-zA-Z0-9._+]+$ ]] || { echo 'Invalid pkgver.' >&2; exit 1; }
    done
    for revision in "$incoming_rel" "$existing_rel"; do
      [[ "$revision" =~ ^[0-9]+([.][0-9]+)*$ ]] || { echo 'Invalid pkgrel.' >&2; exit 1; }
    done
    if (( $(vercmp "$existing_version" "$incoming_version") > 0 )); then
      echo "AUR has newer pkgver ${existing_version}; refusing to overwrite it." >&2
      exit 1
    fi
    if [[ "$existing_version" == "$incoming_version" ]] &&
       (( $(vercmp "$incoming_rel" "$existing_rel") <= 0 )) &&
       ! cmp -s /tmp/generated-PKGBUILD /tmp/local-repo/PKGBUILD; then
      echo 'Changed package requires a strictly higher pkgrel; refusing overwrite.' >&2
      exit 1
    fi
  fi
  cp /tmp/generated-PKGBUILD /tmp/local-repo/PKGBUILD
}
if [[ -n "$assets" ]]; then
  echo 'Copying' $assets
  cp -rt /tmp/local-repo/ $assets
fi
echo '::endgroup::'

if [ "$updpkgsums" == "true" ]; then
  echo '::group::Updating checksums'
  cd /tmp/local-repo/
  updpkgsums
  echo '::endgroup::'
fi

if [ "$test" == "true" ]; then
  echo '::group::Building package with makepkg'
  cd /tmp/local-repo/
  makepkg "${test_flags[@]}"
  echo '::endgroup::'
fi

echo '::group::Generating .SRCINFO'
cd /tmp/local-repo
makepkg --printsrcinfo >.SRCINFO
echo '::endgroup::'

if [ -n "$post_process" ]; then
  echo '::group::Executing post process commands'
  cd /tmp/local-repo/
  eval "$post_process"
  echo '::endgroup::'
fi

echo '::group::Committing files to the repository'
if [[ -z "$assets" ]]; then
  git add -fv PKGBUILD .SRCINFO
else
  git add --all
fi

case "$allow_empty_commits" in
true)
  git commit --allow-empty -m "$commit_message"
  ;;
false)
  if ! git rev-parse --verify HEAD >/dev/null 2>&1 || ! git diff-index --quiet HEAD; then
    git commit -m "$commit_message"
  fi
  ;;
*)
  echo "::error::Invalid Value: inputs.allow_empty_commits is neither 'true' nor 'false': '$allow_empty_commits'"
  exit 2
  ;;
esac
echo '::endgroup::'

echo '::group::Publishing the repository'
git remote add aur "ssh://aur@aur.archlinux.org/${pkgname}.git"
case "$force_push" in
true)
  git push -v --force aur master
  ;;
false)
  git push -v aur master
  ;;
*)
  echo "::error::Invalid Value: inputs.force_push is neither 'true' nor 'false': '$force_push'"
  exit 3
  ;;
esac
echo '::endgroup::'
