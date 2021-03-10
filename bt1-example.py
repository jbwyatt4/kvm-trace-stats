#!/usr/bin/env python3

import sys
from babeltrace import TraceCollection

trace_path = sys.argv[1]

trace_collection = TraceCollection()

trace_collection.add_trace(trace_path, 'ctf')

for event in trace_collection.events:
  print(event.name)