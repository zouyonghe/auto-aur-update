#!/bin/bash

set -o errexit -o pipefail -o nounset

echo '::group::Creating builder user'
useradd --create-home --shell /bin/bash builder
passwd --delete builder
mkdir -p /etc/sudoers.d/
echo "builder  ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/builder
echo '::endgroup::'

echo '::group::Initializing SSH directory'
mkdir -pv /home/builder/.ssh
touch /home/builder/.ssh/known_hosts
cp -v /ssh_config /home/builder/.ssh/config
chown -vR builder:builder /home/builder
chmod -vR 600 /home/builder/.ssh/*
echo '::endgroup::'

# Upstream v2.7.2 used `runuser builder --command ...`, which forwards
# `--command` to bash on util-linux based images and crashes before /build.sh runs.
exec runuser --user builder -- bash -lc /build.sh
