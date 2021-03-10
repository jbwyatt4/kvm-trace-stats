#!/usr/bin/env python3

import babeltrace as btw
import tempfile

# temporary directory holding the CTF trace
trace_path = tempfile.mkdtemp()

print('trace path: {}'.format(trace_path))

# our writer
writer = btw.CTFWriter(trace_path)

# create one default clock and register it to the writer
clock = btw.Clock('my_clock')
clock.description = 'this is my clock'
writer.add_clock(clock)

# create one default stream class and assign our clock to it
stream_class = btw.StreamClass('my_class')
stream_class.clock = clock

# create one default event class
event_class = btw.EventClass('my_event')

# create one 32-bit signed integer field
int32_field_decl = btw.IntegerFieldDeclaration(32)
int32_field_decl.signed = True

# add this field declaration to our event class
event_class.add_field(int32_field_decl, 'my_field')

# register our event class to our stream class
stream_class.add_event_class(event_class)

# create our single event, based on our event class
event = btw.Event(event_class)

# assign an integer value to our single field
event.payload('my_field').value = -23

# create our single stream
stream = writer.create_stream(stream_class)

# append our single event ro our single stream
stream.append_event(event)

# flush the stream
stream.flush()