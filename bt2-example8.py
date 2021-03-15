#!/usr/bin/env python3

import bt2
import sys
import collections

# Accumulates time diff for each event to print the short names of the top 5 running processes on CPU 0 during the whole trace

# Create a trace collection msg iterator from the first cmd arg
msg_it = bt2.TraceCollectionMessageIterator(sys.argv[1])

# This counter dictionary will hold execution times:
#
# Task cmd name -> Total execution time (ns)
exec_times = collections.Counter()

# This holds the last `sched_switch` event time.
last_ns_from_origin = None

for msg in msg_it:
  # `bt2._EventMessageCount` is the Python type of an event msg
  # Only keep such msgs
  if type(msg) is not bt2._EventMessageConst:
    continue

  # An event msg holds a trace event.
  event = msg.event

  # Only check `sched_switch` events.
  if event.name != 'sched_switch':
    continue

  # Keep only events which occurred on CPU 0.
  if event['cpu_id'] != 0:
    continue

  # Get event msg's default clock snapshot's ns from origin val.
  ns_from_origin = msg.default_clock_snapshot.ns_from_origin

  if last_ns_from_origin is None:
    # We start here.
    last_ns_from_origin = ns_from_origin

  # Previous process's short name.
  prev_comm = str(event['prev_comm'])

  # Initialize an entry in our dictionary if not done yet.
  if prev_comm not in exec_times:
    exec_times[prev_comm] = 0

  # Compute previous process's execution time.
  diff_ns = ns_from_origin - last_ns_from_origin

  # Update execution time of this cmd.
  exec_times[prev_comm] += diff_ns

  # Update last event's time.
  last_ns_from_origin = ns_from_origin

# Print top 5
for comm, ns in exec_times.most_common(5):
  print('{:20}{} s'.format(comm, ns / 1e9))