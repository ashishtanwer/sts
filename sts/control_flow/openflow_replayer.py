# Copyright 2011-2013 Colin Scott
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
Tool for replaying OpenFlow messages from a trace.

Motivation for this tool:
 - Delta debugging does not fully minimize traces (often for good reason,
   e.g. delicate timings). We have observed minimized traces often contain many
   OpenFlow messages that time our or are overwritten, i.e. are not directly
   relevent for triggering an invalid network configuratoon.

This tool enables:
  - automatic filtering of flow_mods that timed out or were overwritten by
    later flow_mods.
  - automatic filtering of flow_mods that are irrelevant to a set of flow
    entries specified by the user.
  - interactive bisection of the OpenFlow trace to infer which messages were
    and weren't relevent for triggering the bug (especially useful for tricky
    cases requiring human involvment). (TBD)

The tool can then spit back out a new event trace without the irrelevant
OpenFlow messages.
'''

from pox.openflow.libopenflow_01 import *
from sts.event_dag import EventDag
import sts.input_traces.log_parser as log_parser
from sts.replay_event import ControlMessageReceive
from sts.control_flow.replayer import Replayer
from sts.control_flow.base import *
from sts.util.console import msg

# TODO(cs): need to virtualize time for the software switches to capture flow
# entry timeouts. Currently they call time.time() to get the current time.

# TODO(cs): dump new event traces post-filtering.

# TODO(cs): allow user to specify a set of routings rules of interest (e.g.
# those that form a loop), and filter
# out all messages that were not revelent to setting up those rules.

class OpenFlowReplayer(ControlFlow):
  '''
  Replays OpenFlow messages and filters out messages that are not of interest,
  producing a new event trace file as output.
  '''
  def __init__(self, simulation_cfg, superlog_path_or_dag):
    # TODO(cs): allow the user to specify a stop point in the event dag, in
    # case the point they are interested in occurs before the end of the trace.
    self.simulation_cfg = simulation_cfg
    self.sync_callback = ReplaySyncCallback()
    if type(superlog_path_or_dag) == str:
      superlog_path = superlog_path_or_dag
      # The dag is codefied as a list, where each element has
      # a list of its dependents.
      self.event_list = EventDag(log_parser.parse_path(superlog_path)).events
    else:
      self.event_list = superlog_path_or_dag.events

    self.event_list = [ e for e in self.event_list
                        if type(e) == ControlMessageReceive
                        and type(e.get_packet()) != ofp_packet_out ]

  def simulate(self):
    self.simulation = self.simulation_cfg.bootstrap(self.sync_callback,
                                                    boot_controllers=boot_mock_controllers)
    connect_to_mock_controllers(self.simulation)

    # Reproduce the routing table state.
    for next_event in self.event_list:
      msg.success("Injecting %r" % next_event)
      next_event.manually_inject(self.simulation)

    # now filter out all flow_mods that don't correspond to an entry in the
    # final routing table. Do that by walking backwards through the flow_mods,
    # and checking if they match the flow table. If so, add it to list, and
    # remove all flow entries that currently match it to filter overlapping
    # flow_mods from earlier in the event_list.
    relevent_flow_mods = []
    all_flow_mods = [e for e in self.event_list if type(e.get_packet()) == ofp_flow_mod]
    for last_event in reversed(all_flow_mods):
      switch = self.simulation.topology.get_switch(last_event.dpid)
      if switch.table.matching_entries(last_event.get_packet().match) != []:
        relevent_flow_mods.append(last_event)
        switch.table.remove_matching_entries(last_event.get_packet().match)

    # Now print them in the forward direction.
    msg.interactive("Filtered flow mods:")
    for next_event in reversed(relevent_flow_mods):
      print "%r" % next_event

    return self.simulation
