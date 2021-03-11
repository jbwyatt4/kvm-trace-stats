#!/usr/bin/env python3

import bt2
import sys

# RuntimeError: Some auto source component specs did not produce any component: ~/perf.data
# means it could not find the file

# Get the trace path from the first cmd-line arg
path = sys.argv[1]

# Create a trace collection msg iterator with this path
msg_it = bt2.TraceCollectionMessageIterator(path)

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg
  if type(msg) is bt2._EventMessageConst:
    # An event msg holds a trace event.
    event = msg.event

    # Print event's name.
    print(msg.event.name)