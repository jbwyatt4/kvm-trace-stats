#!/usr/bin/env python3

import sys
import babeltrace

trace_path = sys.argv[1]

trace_collection = babeltrace.reader.TraceCollection()

trace_collection.add_trace(trace_path, 'ctf')

for event in trace_collection.events:
  print(event.name)