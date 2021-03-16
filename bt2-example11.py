#!/usr/bin/env python3

import bt2
import sys

# Get the `source.ctf.fs` component class from the `ctf` plugin.
comp_cls = bt2.find_plugin('ctf').source_component_classes['fs']

# The `babeltrace.support-info` query operation expects a `type`
# parameter (set to `directory` here) and an `input` parameter (the
# actual path or string to check, in this case the first command-line
# argument).
#
# See `babeltrace2-query-babeltrace.support-info(7)`.
params = {
  'type': 'directory',
  'input': sys.argv[1],
}

# Create a query executor.
#
# This is the environment in which query operations happens. The
# queried component class has access to this executor, for example to
# retrieve the query operation's logging level.
query_exec = bt2.QueryExecutor(comp_cls, 'babeltrace.support-info', params)

# Query the component class through the query executor.
#
# This method returns the result.
result = query_exec.query()

# Print the result.
print(result)