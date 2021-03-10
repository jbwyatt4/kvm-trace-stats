#!/usr/bin/env python3

import sys

try:
    from babeltrace import Reader
except ImportError:
    # quick fix for debian-based distros
    sys.path.append("/usr/local/lib/python%d.%d/site-packages" %
                    (sys.version_info.major, sys.version_info.minor))
    from babeltrace import Reader

trace_path = sys.argv[1]

trace_collection = babeltrace.reader.TraceCollection()

trace_collection.add_trace(trace_path, 'ctf')

for event in trace_collection.events:
  print(event.name)