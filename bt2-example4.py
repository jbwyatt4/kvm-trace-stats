#!/usr/bin/env python3

import bt2
import sys

# Can rewrite the trace collection msg iterator using the convenience static method which finds the plugin and component class for you.

# Create a trace collection msg iterator, instantiating a single
# `source.ctf.fs` component class with the `inputs` initialization
# parameter set to open a single CTF trace.
msg_it = bt2.TraceCollectionMessageIterator(
  bt2.ComponentSpec.from_named_plugin_and_component_class('ctf', 'fs', {
    # Get the CTF trace path from the first cmd-line arg
    'inputs': [sys.argv[1]],
  })
)

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg
  if type(msg) is bt2._EventMessageConst:
    # Print event's name.
    print(msg.event.name)