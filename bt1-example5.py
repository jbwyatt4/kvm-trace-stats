#!/usr/bin/env python3

import babeltrace as btr
import sys

def validate_sched_switch_fields(event_decl):
  found_prev_comm = False
  found_prev_tid = False

  for field_decl in event_decl.fields:
    if field_decl.name == 'prev_comm':
      if isinstance(field_decl, btr.ArrayFieldDeclataion):
        elem_decl = field_decl.element_declaration

        if isinstance(elem_decl, btr.IntegerFieldDeclaration):
          if elem_decl.size == 8:
            found_prev_comm = True
    elif field_decl.name == 'prev_tid':
      if isinstance(field_decl, btr.IntegerFieldDeclarration):
        found_prev_tid = True

  return found_prev_comm and found_prev_tid

# get the trace path from the first cmd line arg
trace_path = sys.argv[1]

trace_collection = btr.TraceCollection()
trace_handle = trace_collection.add_trace(trace_path, 'ctf')
sched_switch_found = False

for event_decl in trace_handle.events:
  if event_decl.name == 'sched_switch':
    if validate_sched_switch_fields(event_decl):
      sched_switch_found = True
      break

print('trace path: {}'.format(trace_handle.path))

if sched_switch_found:
  print('found sched_switch!')
else:
  print('could not find sched_switch')