#!/bin/bash
set -euxo pipefail

ARGUMENTS="$*"
trap 'echo "ERROR: ${BASH_SOURCE:-$BASH_COMMAND in $0}: ${FUNCNAME[0]:-line} at line: $LINENO, arguments: $ARGUMENTS" 1>&2; exit 1' ERR

if [[ "${EUID}" -eq "0" ]]; then
  echo >&2 "err: do not run this as root"
  exit 1
fi

pushd "$(mktemp -d)"

# removing debian/ubuntu-packaged-openconnect
sudo apt-get remove openconnect vpnc-scripts libopenconnect5

# building vpnc-scripts
# https://www.infradead.org/openconnect/vpnc-script.html
git clone --depth 1 https://gitlab.com/openconnect/vpnc-scripts.git
rm -rf vpnc-scripts/.git/
sudo cp -vR vpnc-scripts /usr/share/
sudo mkdir -p /etc/vpnc/pre-init.d/
sudo mkdir -p /etc/vpnc/connect.d/
sudo mkdir -p /etc/vpnc/post-connect.d/
sudo mkdir -p /etc/vpnc/disconnect.d/
sudo mkdir -p /etc/vpnc/post-disconnect.d/
sudo mkdir -p /etc/vpnc/attempt-reconnect.d/
sudo mkdir -p /etc/vpnc/reconnect.d/

# building openconnect
# https://www.infradead.org/openconnect/building.html
# https://gitlab.com/openconnect/openconnect/-/blob/master/.gitlab-ci.yml

sudo apt-get build-dep openconnect libopenconnect5

# [--with-openssl] configure: error: Could not build against OpenSSL
sudo apt install libssl-dev

git clone --depth 1 https://gitlab.com/openconnect/openconnect.git

pushd openconnect
./autogen.sh
#./configure
./configure --without-gnutls --with-openssl --with-java
make -j8
make -j8 check || true
sudo make install
sudo ldconfig
popd # openconnect

popd # mktemp
