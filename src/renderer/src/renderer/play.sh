#!/bin/bash

cat <<EOF | while read -r cmd; do sleep 1; echo $cmd; done
send a1 a2 EHLO
recv a2 a1
mark a2 "purple"
send a2 a3 EHLO
send a1 a3 EHLO
recv a3 a2
mark a3 "purple"
send a3 a4 EHLO
send a1 a2 END
send a1 a3 END
recv a3 a1
recv a3 a1
unmark a3
recv a4 a3
send a3 a4 END
recv a2 a1
mark a4 "purple"
unmark a2
recv a4 a3
unmark a4
EOF

sleep 2
echo "quit"