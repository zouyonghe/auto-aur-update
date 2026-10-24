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
ssh-keyscan -v -t "$ssh_keyscan_types" aur.archlinux.org >>~/.ssh/known_hosts
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
if git clone -v "https://aur.archlinux.org/${pkgname}.git" /tmp/local-repo; then
  echo 'Cloned existing AUR package.'
else
  echo 'AUR package does not exist yet; initializing first publication.'
  rm -rf /tmp/local-repo
  mkdir -p /tmp/local-repo
  git -C /tmp/local-repo init
  git -C /tmp/local-repo checkout -b master
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
    if (( $(vercmp "$existing_version" "$incoming_version") > 0 )); then
      echo "AUR has newer pkgver ${existing_version}; refusing to overwrite it." >&2
      exit 1
    fi
    if [[ "$existing_version" == "$incoming_version" ]] && (( $(vercmp "$existing_rel" "$incoming_rel") > 0 )); then
      sed -i "s/^pkgrel=.*/pkgrel=${existing_rel}/" /tmp/generated-PKGBUILD
      echo "Preserved newer AUR pkgrel ${existing_rel}."
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
  git diff-index --quiet HEAD || git commit -m "$commit_message"
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
