#!/usr/bin/env python3

from babeltrace import TraceCollection
import sys

trace_collection = TraceCollection()

for path in sys.argv[1:]:
  trace_collection.add_trace(path, 'ctf')

for event in trace_collection.events:
  if 'sched_switch' in event:
    print(event['sched_switch'])