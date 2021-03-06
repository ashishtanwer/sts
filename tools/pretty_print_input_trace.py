#!/usr/bin/env python

# note: must be invoked from the top-level sts directory

import time
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import sts.replay_event as replay_events
from sts.dataplane_traces.trace import Trace
from sts.input_traces.log_parser import parse

default_fields = ['class_with_label', 'fingerprint', 'event_delimiter']
default_filtered_classes = set()

def class_printer(event):
  print event.__class__.__name__

def class_with_label_printer(event):
  print (event.label + ' ' + event.__class__.__name__ +
         ' (' + ("prunable" if event.prunable else "unprunable") + ')')

def round_printer(event):
  print "round: %d" % event.round

def fingerprint_printer(event):
  fingerprint = None
  if hasattr(event, 'fingerprint'):
    # the first element of the fingerprint tuple is always the class name, so
    # we skip it over
    # TODO(cs): make sure that dict fields are always in the same order
    fingerprint = event.fingerprint[1:]
  print "fingerprint: ", fingerprint

def _timestamp_to_string(timestamp):
  sec = timestamp[0]
  micro_sec = timestamp[1]
  epoch = float(sec) + float(micro_sec) / 1e6
  struct_time = time.localtime(epoch)
  # hour:minute:second
  no_micro = time.strftime("%X", struct_time)
  # hour:minute:second:microsecond
  with_micro = no_micro + ":%d" % micro_sec
  return with_micro

def abs_time_printer(event):
  print _timestamp_to_string(event.time)

def event_delim_printer(_):
  print "--------------------------------------------------------------------"

field_formatters = {
  'class_with_label' : class_with_label_printer,
  'class' : class_printer,
  'fingerprint' : fingerprint_printer,
  'event_delimiter' : event_delim_printer,
  'abs_time' : abs_time_printer,
  # TODO(cs): allow user to display relative time between events
}

class Stats:
  def __init__(self):
    self.input_events = {}
    self.internal_events = {}

  def update(self, event):
    if isinstance(event, replay_events.InputEvent):
      event_name = str(event.__class__.__name__)
      if event_name in self.input_events.keys():
        self.input_events[event_name] += 1
      else:
        self.input_events[event_name] = 1
    else:
      event_name = str(event.__class__.__name__)
      if event_name in self.internal_events.keys():
        self.internal_events[event_name] += 1
      else:
        self.internal_events[event_name] = 1

  @property
  def input_event_count(self):
    input_count = 0
    for count in self.input_events.values():
      input_count += count
    return input_count

  @property
  def internal_event_count(self):
    internal_count = 0
    for count in self.internal_events.values():
      internal_count += count
    return internal_count

  @property
  def total_event_count(self):
    return self.input_event_count + self.internal_event_count

  def __str__(self):
    s = "Events: %d total (%d input, %d internal).\n" % (self.total_event_count, self.input_event_count, self.internal_event_count)
    if len(self.input_events) > 0:
      s += "\n\tInput events:\n"
      for event_name, count in self.input_events.items():
        s += "\t  %s : %d\n" % (event_name, count)
    if len(self.internal_events) > 0:
      s += "\n\tInternal events:\n"
      for event_name, count in self.internal_events.items():
        s += "\t  %s : %d\n" % (event_name, count)
    return s

def main(args):
  def load_format_file(format_file):
    if format_file.endswith('.py'):
      format_file = format_file[:-3].replace("/", ".")
    config = __import__(format_file, globals(), locals(), ["*"])
    return config

  if args.format_file is not None:
    format_def = load_format_file(args.format_file)
  else:
    format_def = object()

  dp_trace = None
  if args.dp_trace_path is not None:
    dp_trace = Trace(args.dp_trace_path).dataplane_trace

  if hasattr(format_def, "fields"):
    fields = format_def.fields
  else:
    fields = default_fields

  for field in fields:
    if field not in field_formatters:
      raise ValueError("unknown field %s" % field)

  if hasattr(format_def, "filtered_classes"):
    filtered_classes = format_def.filtered_classes
  else:
    filtered_classes = default_filtered_classes

  stats = Stats()

  # all events are printed with a fixed number of lines, and (optionally)
  # separated by delimiter lines of the form:
  # ----------------------------------
  with open(args.input) as input_file:
    trace = parse(input_file)
    for event in trace:
      if type(event) not in filtered_classes:
        if dp_trace is not None and type(event) == replay_events.TrafficInjection:
          event.dp_event = dp_trace.pop(0)
        for field in fields:
          field_formatters[field](event)
        stats.update(event)

  if args.stats:
    print "Stats: %s" % stats

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('input', metavar="INPUT",
                      help='The input json file to be printed')
  parser.add_argument('-f', '--format-file',
                      help=str('''The output format configuration file.'''
  ''' ----- config file format: ----'''
  ''' config files are python modules that may define the following variables: '''
  '''   fields  => an array of field names to print. uses default_fields if undefined. '''
  '''   filtered_classes => a set of classes to ignore, from sts.replay_event'''
  '''   ... '''
  ''' see example_pretty_print_config.py for an example. '''
  ''' ---------------------------------'''),
                      default=None)
  parser.add_argument('-n', '--no-stats', action="store_false", dest="stats",
                      help="don't print statistics",
                      default=True)
  parser.add_argument('-d', '--dp-trace-path', dest="dp_trace_path",
                      help="for older traces, specify path to the TrafficInjection packets",
                      default=None)
  args = parser.parse_args()

  main(args)
