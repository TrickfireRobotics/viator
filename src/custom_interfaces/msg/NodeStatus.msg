# node's own report of whether it is working, published to /viator/node_status
# nodes republish this periodically so a node that has died can be detected

uint8 STARTING=0
uint8 OK=1
uint8 DEGRADED=2
uint8 FAILED=3

# logical module name
string name

# one of the constants above
uint8 state

# human-readable context
# example: "6 motors on can0"
string detail
