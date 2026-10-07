# A node's own report of whether it is working, published to /viator/node_status.
#
# Nodes republish this periodically rather than only on change, so a node that has died
# stops reporting and the supervisor can tell "stopped" apart from "last said it was fine".

uint8 STARTING=0
uint8 OK=1
uint8 DEGRADED=2
uint8 FAILED=3

# Logical module name, e.g. "can_rmdx8". Matches the names the supervisor expects.
string name

# One of the constants above.
uint8 state

# Short human-readable context, e.g. "6 motors on can1". May be empty.
string detail
