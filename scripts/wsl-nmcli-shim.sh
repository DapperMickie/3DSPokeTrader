#!/bin/sh
# WSL does not run NetworkManager. The Switch adapter is dedicated to the
# bridge, so there is no manager to release it from before bringing it down.
if [ "$#" -eq 5 ] && [ "$1" = device ] && [ "$2" = set ] && \
   [ "$4" = managed ] && { [ "$5" = no ] || [ "$5" = yes ]; }; then
    exit 0
fi
echo "Unsupported nmcli shim invocation" >&2
exit 2
