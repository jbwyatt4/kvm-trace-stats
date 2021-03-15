#!/usr/bin/env python3

import bt2
import sys
import datetime

# Get an event's time

# Create a trace collection msg iterator from the first cmd arg
msg_it = bt2.TraceCollectionMessageIterator(sys.argv[1])

# Last event's time (ns from origin).
last_event_ns_from_origin = None

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg
  if type(msg) is bt2._EventMessageConst:
    # Get event msg's default clock snapshot's ns from origin
    # value
    ns_from_origin = msg.default_clock_snapshot.ns_from_origin

    # Compute the time difference since the last event msg.
    diff_s = 0

    if last_event_ns_from_origin is not None:
      diff_s = (ns_from_origin - last_event_ns_from_origin) / 1e9

    # Create a `datetime.datetime` object from
    # `ns_from_origin` for presentation. Note that such an
    # object is less accurate than `ns_from_origin` as it
    # holds microseconds, not nanoseconds.
    dt = datetime.datetime.fromtimestamp(ns_from_origin / 1e9)

    # Print line.
    fmt = '{} (+{:.6f} s): {}'
    print(fmt.format(dt, diff_s, msg.event.name))

    # Update last event's time.
    last_event_ns_from_origin = ns_from_origin

  else:
    pass#print(msg)

# Warning
# This printed from epoch-need to fix
# -
# 1970-01-01 00:27:00.078884 (+0.000014 s): sched:sched_waking
# 1970-01-01 00:27:00.078904 (+0.000020 s): sched:sched_switch
# 1970-01-01 00:27:00.078918 (+0.000014 s): sched:sched_switch
# 1970-01-01 00:27:00.078933 (+0.000015 s): sched:sched_switch
# 1970-01-01 00:27:00.582873 (+0.503940 s): sched:sched_waking
