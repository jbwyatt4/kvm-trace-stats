#!/usr/bin/env python3

import bt2

# RuntimeError: Some auto source component specs did not produce any component: ~/perf.data

for msg in bt2.TraceCollectionMessageIterator('~/ctf'):
  if type(msg) is bt2._EventMessageConst:
    print(msg.event.name)