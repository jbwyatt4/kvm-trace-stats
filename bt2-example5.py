#!/usr/bin/env python3

import bt2
import sys

# Get a specific event field's value

# _ means you cannot instantiate such a class (can not call the class), you can compare against an object type
# if type(msg) is bt2._EventMessageConst:
# or
# if isinstance(field, bt2._IntegerFieldConst):

# Create a trace collection msg iterator from the first
# cmd-line arg
msg_it = bt2.TraceCollectionMessageIterator(sys.argv[1])

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg.
  # Only keep such msgs.
  if type(msg) is not bt2._EventMessageConst:
    continue

  # An event msg holds a trace event.
  event = msg.event

  # Only check `sched_switch` events.
  if event.name != 'sched_switch':
    print(event.name) # name is sched:sched_switch, assuming LTTng uses sched_switch
    continue

  # In an LTTng trace, the `cpu_id` field is a packet context field
  # The mapping interface of `event` can still find it
  cpu_id = event['cpu_id']

  # Previous and next process short names are found in the event's
  # `prev_comm` and `next_comm` fields.
  prev_comm = event['prev_comm']
  next_comm = event['next_comm']

  # Print line, using field values.
  msg = 'CPU {}: Switching process `{}` → `{}`'
  print(msg.format(cpu_id, prev_comm, next_comm))