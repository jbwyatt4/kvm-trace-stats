#!/usr/bin/env python3

import bt2
import sys

# Print event payload if it exists

# Create a trace collection msg iterator from the first cmd arg
msg_it = bt2.TraceCollectionMessageIterator(sys.argv[1])

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg
  if type(msg) is bt2._EventMessageConst:
    # Check if the `fd` event payload field exists.
    if 'fd' in msg.event.payload_field:
      # Print the `fd` event payload field's value.
      print(msg.event.payload_field['fd'])
  else:
    print(msg)

# Example of what else prints
# <bt2.message._StreamBeginningMessageConst object @ 0x2976d80>
# <bt2.message._StreamBeginningMessageConst object @ 0x2980000>
# <bt2.message._PacketBeginningMessageConst object @ 0x2976e40>
# <bt2.message._PacketBeginningMessageConst object @ 0x29800c0>
# <bt2.message._PacketEndMessageConst object @ 0x298cf00>
# <bt2.message._StreamEndMessageConst object @ 0x298cf60>
# <bt2.message._PacketEndMessageConst object @ 0x298d0d0>
# <bt2.message._StreamEndMessageConst object @ 0x298d130>
