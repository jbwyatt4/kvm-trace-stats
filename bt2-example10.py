#!/usr/bin/env python3

import bt2
import sys

# Create an empty graph.
graph = bt2.Graph()

# Add a `source.text.dmesg` component.
#
# graph.add_component() returns the created and added component.
#
# Such a component reads Linux kernel ring buffer messages (see
# `dmesg(1)`) from the standard input and creates corresponding event
# messages. See `babeltrace2-source.text.dmesg(7)`.
#
# `my source` is the unique name of this component within `graph`.
comp_cls = bt2.find_plugin('text').source_component_classes['dmesg']
src_comp = graph.add_component(comp_cls, 'my source')

# Add a `sink.text.pretty` component.
#
# Such a component pretty-prints event msgs on the standard
# output (one msg per line). See `babeltrace2-sink.text.pretty(7)`.
# The `babeltrace2 convert` CLI cmd uses a `sink.text.prety`
# sink component by default.
comp_cls = bt2.find_plugin('text').sink_component_classes['pretty']
sink_comp = graph.add_component(comp_cls, 'my sink')

# Connect the `out` output port of the `source.text.dmesg`
# component to the `in` input port of the `sink.text.pretty`
# component.
graph.connect_ports(src_comp.output_ports['out'],
                    sink_comp.input_ports['in'])

# Run the trace processing graph.
graph.run()