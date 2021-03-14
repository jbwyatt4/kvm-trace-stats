#!/usr/bin/env python3

import bt2
import sys

# Find the `ctf` plugin (shipped with Babeltrace 2).
ctf_plugin = bt2.find_plugin('ctf')

# Get the `source.ctf.fs` component class fromt he plugin.
fs_cc = ctf_plugin.source_component_classes['fs']

# Create a trace collection msg interator, instantiating a single
# `source.ctf.fs` component class with the `inputs` initialization
# parameter set to open a single CTF trace.
msg_it = bt2.TraceCollectionMessageIterator(bt2.ComponentSpec(fs_cc,{
  # Get the CTF trace pathf rom the first cmd-line arg
  'inputs': [sys.argv[1]]
}))

# Iterate the trace msgs
for msg in msg_it:
  # `bt2._EventMessageConst` is the Python type of an event msg
  if type(msg) is bt2._EventMessageConst:
    # Print event's name.
    print(msg.event.name)