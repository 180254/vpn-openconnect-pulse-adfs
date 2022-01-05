What is this:
  Wrapper that allows you to log into the PulseSecure VPN server, secured with MSFT SSO, using the OpenConnect VPN client.

How it works:
  To log into the Pulse Secure VPN server you need a cookie named "DSID". The tool opens the browser and then clicks through the website (the playwright enters login information). Next, the tool acquires the cookie needed to log into the VPN server (DSID cookie). Finally, the openconnect logs into the Pulse Secure VPN using the cookie provided to it. It is a comprehensive solution for VPN connectivity. You may be interested in the whole thing or part of it.

Components of the solution:
    - vpn-openconnect - Entrypoint. Allows to change the default version of the solution, currently calls vpn-openconnect-adfs4.
    - vpn-adfs-cookie4.py - Obtains the DSID cookie (clicks for you in the browser).
    - vpn-openconnect-adfs4 - First calls vpn-adfs-cookie4.py to get the cookie, then runs openconnect with that cookie.
    - vpn-set-routing-full - Handles "full" (non-split) routing mode (all traffic is routed through the VPN server).
    - vpn-set-routing-split - Handles "split" routing mode (part of the traffic is routed through the VPN server).
    - vpn-custom-routings.txt - "Split" mode helper. Stores a list of domains to include them in split mode.
    - vpn-custom-routings - Takes the "vpn-custom-routings.txt" file, and updates "vpn-set-routing-split" file.
    - vpn-adhoc-routing - Adds a new "split routing" rule at runtime.

Dependency installation (on the Debian-based OS):
    $ ./install-openconnect.sh
    $ sudo apt-get install python3 python3-pip python3-venv
    $ python3 -m venv venv
    $ venv/bin/pip3 install --upgrade pip wheel setuptools
    $ venv/bin/pip3 install --upgrade -r requirements.txt
    $ venv/bin/python3 -m playwright install

How to get started:
    - Configure python keyring (https://pypi.org/project/keyring/). Store credentials there that allow you to connect to the VPN server there.
      $ keyring set "vpnadfscreds" "email"    # name.surname@example.com
      $ keyring set "vpnadfscreds" "password" # password
      $ keyring set "vpnadfscreds" "totp"     # totpBase32Secret
    - Edit the "vpn-openconnect-adfs4" file. Fill in the VPN server address there.
    - Edit the "vpn-openconnect-adfs4" file. Check the openconnect parameters and change them if you need to.
    - Edit the "vpn-set-routing-split" file. In the "split routing rules" section, enter a list of ip+netmask routed through a VPN server in the split mode.
    - Edit the "vpn-custom-routings.txt" file. Enter a list of domains routed through a VPN server in split mode.
    - Optionally, add "vpn-openconnect-adfs4" script to the sudoers file.

How to run it:
    ./vpn-openconnect [--mode full|split] [--protocol nc|pulse|other(?)] [--browser chromium|firefox|webkit] [--headless true|false]
    ./vpn-custom-routings fix - Reloads vpn-custom-routings.txt-related entries in the vpn-set-routing-split file.
    ./vpn-adhoc-routing some.example.com - Passes some.example.com through VPN server on a runtime.

Notes:
    - ***Do NOT share the DSID value with anyone.***
    - "--headless false" option allows you to check what's going on in the browser and debug problems.
    - If something doesn't work, check the rules in the vpn-adfs-cookie4.py file in the TaskLoop class. You may need to adapt them to work with your VPN server.

Troubleshooting:
    - Fixing /etc/resolv.conf:
      $ sudo systemctl restart systemd-resolved.service

Alternative solutions:
    - https://github.com/utknoxville/openconnect-pulse-gui
    - https://gitlab.com/openconnect/openconnect/-/merge_requests/271

Trademark notes:
    - Pulse Secure, Pulse, and Steel-Belted Radius are registered trademarks of Pulse Secure, LLC. in the United States and other countries.
    - openconnect means the OpenConnect VPN client (www.infradead.org/openconnect/).
