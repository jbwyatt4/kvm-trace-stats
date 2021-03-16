#!/usr/bin/env python3

import bt2
import sys

# Inspect event classes
# each event stream is a stream class instance

# This example shows how to list all the event classes of a stream class. Will also print for every event class the names of its payload field class's first-level members.

# Create a trace collection msg iterator from the first cmd arg
msg_it = bt2.TraceCollectionMessageIterator(sys.argv[1])

# Get the msg iterator's first stream beginning msg.
for msg in msg_it:
  # `bt2._StreamBeginningMessageCount` is the Python type of a stream beginning msg.
  if type(msg) is bt2._StreamBeginningMessageConst:
    break

# A stream beginning msg holds a stream.
stream = msg.stream

# Get the stream's class.
stream_class = stream.cls

# The stream class object offers a mapping interface (like a
# read-on `dict`), where keys are event class IDs and values
# are `bt2._EventClassConst` objects.
for event_class in stream_class.values():
  print('{}:'.format(event_class.name))

  # The `payload_field_class` property of an event class
  # returns a `bt2._StructureFieldClassConst` object. This
  # object offers a mapping interface, where keys are member
  # names and values are
  # `bt2._StructureFieldClassMemberConst` objects.
  for member in event_class.payload_field_class.values():
    fmt = '   {}: `{}.{}`'
    print(fmt.format(member.name, bt2.__name__,
                     member.field_class.__class__.__name__))