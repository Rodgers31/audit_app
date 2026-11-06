#!/bin/sh
# Called only in an owned local container, network=none, with sealed debs mounted
# read-only at /native-debs. native_artifacts.py verifies every input first.
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/tmp
export LC_ALL=C.UTF-8
export DEBIAN_FRONTEND=noninteractive
export PYTHONDONTWRITEBYTECODE=1
dpkg --install /native-debs/*.deb
