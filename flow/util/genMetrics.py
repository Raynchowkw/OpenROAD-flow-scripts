#!/usr/bin/env python3

# This scripts attempts to extract relevant data from a completed flow design
# and save it into a "metadata.json". It achieves this by looking for specific
# information in specific files using regular expressions
#-------------------------------------------------------------------------------

import os
from sys import exit
from datetime import datetime, timedelta
from uuid import uuid4 as uuid
from subprocess import check_output, call, STDOUT

import argparse
import json
import pandas as pd
import re

# Parse and validate arguments
# ==============================================================================
def parse_args():
  parser = argparse.ArgumentParser(
      description='Generates metadata from OpenROAD flow')
  parser.add_argument('--flowPath', '-f', required=False, default="./",
                      help='Path to the flow directory')
  parser.add_argument('--design', '-d', required=False, default="all_designs",
                      help='Design Name for metrics')
  parser.add_argument('--flowVariant', '-v', required=False, default="base",
                      help='FLOW_VARIANT for the design')
  parser.add_argument('--platform', '-p', required=False, default="nangage45",
                      help='Design Platform')
  parser.add_argument('--comment', '-c', required=False, default="",
                      help='Additional comments to embed')
  parser.add_argument('--output', '-o', required=False, default="metadata.json",
                      help='Output file')
  args = parser.parse_args()

  if not os.path.isdir(args.flowPath):
    print("Error: flowPath does not exist")
    print("Path: " + args.flowPath)
    exit(1)

  return args


# Functions
# ==============================================================================
# Main function to do specific extraction of patterns from a file

# This function will look for a regular expression "pattern" in a "file", and
# set the key, "jsonTag", to the value found. The specific "occurrence" selects
# which occurrence it uses (default -1, i.e., last). If pattern not found, it
# will print an error and set the value to N/A. If a "defaultNotFound" is set,
# it will use that instead.  If count is set to True, it will return the count
# of the pattern.

def extractTagFromFile(jsonTag, jsonFile, pattern, file, count=False, occurrence=-1, defaultNotFound="N/A", t=str):
  if jsonTag in jsonFile:
    print("[WARN] Overwriting Tag", jsonTag)

  # Open file
  try:
    searchFilePath = os.path.join(args.flowPath, file)
    with open(searchFilePath) as f:
      content = f.read()

    m = re.findall(pattern, content, re.M)

    if m:
      if count:
        # Return the count
        jsonFile[jsonTag] = len(m)
      else:
        # Note: This gets the specified occurrence
        value = m[occurrence]
        if isinstance(value, tuple):
          value = value[arrayPos]
        value = value.strip()
        try:
          jsonFile[jsonTag] = float(value)
        except:
          jsonFile[jsonTag] = str(value)
    else:
      # Only print a warning if the defaultNotFound is not set
      if defaultNotFound == "N/A":
        print("[WARN] Tag", jsonTag, "not found in", searchFilePath)
      jsonFile[jsonTag] = defaultNotFound
  except IOError:
    print("[WARN] Failed to open file:", searchFilePath)
    jsonFile[jsonTag] = "ERR"


def extractGnuTime(prefix, jsonFile, file):
  extractTagFromFile(prefix + "__runtime__total", jsonFile,
                     "^(\S+)elapsed \S+CPU \S+memKB",
                     file)
  extractTagFromFile(prefix + "__cpu__total", jsonFile,
                     "^\S+elapsed (\S+)CPU \S+memKB",
                     file)
  extractTagFromFile(prefix + "__mem__peak", jsonFile,
                     "^\S+elapsed \S+CPU (\S+)memKB",
                     file)


#
# Extract Clock Latency, Skew numbers
# Need to extract these from native json
#
def get_skew_latency(file_name):
  f = None
  try:
    f = open(file_name, 'r')
  except IOError:
    print("[WARN] Failed to open file:", file_name)
    return ("ERR","ERR","ERR")

  lines = f.readlines()
  f.close()

  latency_section = False
  latency_max = latency_min = skew = 0.0
  worst_latency_max = worst_latency_min = worst_skew = 0.0

  for line in lines:
    if len(line.split())<1:
      continue
    if line.startswith('Latency'):
      latency_section = True
      continue
    if latency_section and len(line.split())==1:
      latency_max = float(line.split()[0])
      continue
    if latency_section and len(line.split())>2:
      latency_min = float(line.split()[0])
      skew = float(line.split()[2])
      if skew > worst_skew:
          worst_skew = skew
          worst_latency_max = latency_max
          worst_latency_min = latency_min
      latency_section = False

  return(worst_latency_max, worst_latency_min, worst_skew)



#
#  Extract clock info from sdc file
#
def read_sdc(file_name):
  clkList = []
  sdcFile = None

  try:
    sdcFile = open(file_name, 'r')
  except IOError:
    print("[WARN] Failed to open file:", file_name)
    return clkList

  lines = sdcFile.readlines()
  sdcFile.close()

  for line in lines:
    if len(line.split())<2:
      continue
    if line.split()[0]=='create_clock':
      clk_idx = line.split().index('-name')
      clkName = line.split()[clk_idx+1]
      period_idx = line.split().index('-period')
      period = line.split()[period_idx+1]

      clk = "%s: %s"%(clkName, period)
      clkList.append(clk)


  clkList.sort()
  return clkList


# Main
# ==============================================================================

def is_git_repo(folder=None):
    cmd = ["git", "branch"]
    if folder is not None:
        return call(cmd, stderr=STDOUT, stdout=open(os.devnull, 'w'), cwd=folder) == 0
    else:
        return call(cmd, stderr=STDOUT, stdout=open(os.devnull, 'w')) == 0

def extract_metrics(cwd, platform, design, flow_variant, output):
    logPath = os.path.join(cwd, "logs", platform, design, flow_variant)
    rptPath = os.path.join(cwd, "reports", platform, design, flow_variant)
    resultPath = os.path.join(cwd, "results", platform, design, flow_variant)

    metrics_dict = {}
    metrics_dict["run__flow__generate__date"] = now.strftime("%Y-%m-%d %H:%M")
    cmdOutput = check_output(['openroad', '-version'])
    cmdFields = [ x.decode('utf-8') for x in cmdOutput.split()  ]
    metrics_dict["run__flow__openroad__version"] = str(cmdFields[0])
    if len(cmdFields) > 1:
      metrics_dict["run__flow__openroad__commit"] = str(cmdFields[1])
    else:
      metrics_dict["run__flow__openroad__commit"] = "N/A"
    if is_git_repo():
        cmdOutput = check_output(['git', 'rev-parse', 'HEAD'])
        cmdOutput = cmdOutput.decode('utf-8').strip()
    else:
        cmdOutput = 'not a git repo'
        print('[WARN]', cmdOutput)
    metrics_dict["run__flow__scripts__commit"] = cmdOutput
    metrics_dict["run__flow__uuid"] = str(uuid())
    metrics_dict["run__flow__design"] = design
    metrics_dict["run__flow__platform"] = platform
    platformDir = os.environ.get('PLATFORM_DIR')
    if platformDir is None:
        print('[INFO]', 'PLATFORM_DIR env variable not set')
        cmdOutput = 'N/A'
    elif is_git_repo(folder=platformDir):
        cmdOutput = check_output(['git', 'rev-parse', 'HEAD'], cwd=platformDir)
        cmdOutput = cmdOutput.decode('utf-8').strip()
    else:
        print('[WARN]', 'not a git repo')
        cmdOutput = 'N/A'
    metrics_dict["run__flow__platform__commit"] = cmdOutput
    metrics_dict["run__flow__variant"] = flow_variant

# Synthesis
# ==============================================================================

    extractTagFromFile("synth__design__instance__stdcell__count", metrics_dict,
                       "Number of cells: +(\S+)",
                       rptPath+"/synth_stat.txt")

    extractTagFromFile("synth__design__instance__stdcell__area", metrics_dict,
                       "Chip area for module.*: +(\S+)",
                       rptPath+"/synth_stat.txt")

    extractGnuTime("synth", metrics_dict, logPath+"/1_1_yosys.log")

# Clocks
#===============================================================================

    clk_list = read_sdc(resultPath+"/2_floorplan.sdc")
    metrics_dict["constraints__clocks__count"] = len(clk_list)
    metrics_dict["constraints__clocks__details"] = clk_list

# Floorplan
# ==============================================================================

    extractTagFromFile("floorplan__timing__setup__tns", metrics_dict,
                       "^tns (\S+)",
                       logPath+"/2_1_floorplan.log")

    extractTagFromFile("floorplan__timing__setup__wns", metrics_dict,
                       "^wns (\S+)",
                       logPath+"/2_1_floorplan.log", occurrence=0)

    extractTagFromFile("floorplan__design__instance__stdcell__area", metrics_dict,
                       "^Design area (\S+) u\^2",
                       logPath+"/2_1_floorplan.log")

    extractTagFromFile("floorplan__design__instance__design__util", metrics_dict,
                       "^Design area.* (\S+)% utilization",
                       logPath+"/2_1_floorplan.log")

    extractTagFromFile("floorplan__design__io__count", metrics_dict,
                       "Num of I/O +(\d+)",
                       logPath+"/3_2_place_iop.log")

    extractTagFromFile("floorplan__design__instance__macros__count", metrics_dict,
                       "Extracted # Macros: (\S+)",
                       logPath+"/2_4_mplace.log", defaultNotFound=0)

    extractGnuTime("floorplan", metrics_dict, logPath+"/2_4_mplace.log")

# Place
# ==============================================================================

    extractTagFromFile("globalplace__route__wirelength__estimated", metrics_dict,
                       "Total wirelength: (\S+)",
                       logPath+"/3_1_place_gp.log")

    extractTagFromFile("globalplace__timing__setup__tns", metrics_dict,
                      "^tns (\S+)",
                      logPath+"/3_1_place_gp.log")

    extractTagFromFile("globalplace__timing__setup__wns", metrics_dict,
                      "^wns (\S+)",
                      logPath+"/3_1_place_gp.log")

    extractGnuTime("globalplace", metrics_dict, logPath+"/3_1_place_gp.log")

    extractTagFromFile("placeopt__timing__setup__tns", metrics_dict,
                       "^tns (\S+)",
                       logPath+"/3_3_resizer.log")

    extractTagFromFile("placeopt__timing__setup__wns", metrics_dict,
                       "^wns (\S+)",
                       logPath+"/3_3_resizer.log")

    extractTagFromFile("placeopt__design__instance__design__area", metrics_dict,
                       "^Design area (\S+) u\^2",
                       logPath+"/3_3_resizer.log")

    extractTagFromFile("placeopt__design__instance__design__util", metrics_dict,
                       "^Design area.* (\S+)% utilization",
                       logPath+"/3_3_resizer.log")

    extractTagFromFile("placeopt__design__instance__stdcell__count", metrics_dict,
                       "^instance_count\n-*\n^(\S+)",
                       logPath+"/3_3_resizer.log")

    extractGnuTime("placeopt", metrics_dict, logPath+"/3_3_resizer.log")

    extractTagFromFile("detailedplace__timing__setup__tns", metrics_dict,
                       "^tns (\S+)",
                       logPath+"/3_4_opendp.log")

    extractTagFromFile("detailedplace__timing__setup__wns", metrics_dict,
                       "^wns (\S+)",
                       logPath+"/3_4_opendp.log")

    extractTagFromFile("detailedplace__design__instance__displacement", metrics_dict,
                       "total displacement +(\d*\.?\d*)",
                       logPath+"/3_4_opendp.log")

    extractTagFromFile("detailedplace__design__instance__displacement__mean", metrics_dict,
                       "average displacement +(\d*\.?\d*)",
                       logPath+"/3_4_opendp.log")

    extractTagFromFile("detailedplace__desgin__instance__displacement__max", metrics_dict,
                       "max displacement +(\d*\.?\d*)",
                       logPath+"/3_4_opendp.log")

    extractTagFromFile("detailedplace__route__wirelength__estimated", metrics_dict,
                       "legalized HPWL +(\d*\.?\d*)",
                       logPath+"/3_4_opendp.log")

    extractGnuTime("detailedplace", metrics_dict, logPath+"/3_4_opendp.log")

# CTS
# ==============================================================================

    latency_max,latency_min,skew = get_skew_latency(logPath+"/4_1_cts.log")
    metrics_dict['cts__clock__latency__min'] = latency_min
    metrics_dict['cts__clock__latency__max'] = latency_max
    metrics_dict['cts__clock__skew__worst'] = skew

    extractTagFromFile("cts__timing__setup__tns__prerepair", metrics_dict,
                       "^post cts-pre-repair.*report_tns\n^-*\n^tns (\S+)",
                       logPath+"/4_1_cts.log")

    extractTagFromFile("cts__timing__setup__wns__prerepair", metrics_dict,
                       "^post cts-pre-repair.*report_wns\n^-*\n^wns (\S+)",
                       logPath+"/4_1_cts.log")

    extractTagFromFile("cts__timing__setup__tns", metrics_dict,
                       "^post cts.*report_tns\n^-*\n^tns (\S+)",
                       logPath+"/4_1_cts.log")

    extractTagFromFile("cts__timing__setup__wns", metrics_dict,
                       "^post cts.*report_wns\n^-*\n^wns (\S+)",
                       logPath+"/4_1_cts.log")

    extractTagFromFile("cts__design__instance__hold_buffer__count", metrics_dict,
                       "Inserted (\d+) hold buffers",
                       logPath+"/4_1_cts.log")

# Route
# ==============================================================================

    latency_max,latency_min,skew = get_skew_latency(logPath+"/5_1_fastroute.log")
    #print(f'skew = {skew}, latency_max = {latency_max}, latency_min = {latency_min}')
    metrics_dict['globalroute__clock__latency__min'] = latency_min
    metrics_dict['globalroute__clock__latency__max'] = latency_max
    metrics_dict['globalroute__clock__skew__worst'] = skew

    extractTagFromFile("globalroute__timing__setup__tns", metrics_dict,
                      "^tns (\S+)",
                      logPath+"/5_1_fastroute.log")

    extractTagFromFile("globalroute__timing__setup__wns", metrics_dict,
                      "^wns (\S+)",
                      logPath+"/5_1_fastroute.log")

    extractTagFromFile("globalroute__timing__clock__slack", metrics_dict,
                      "^\[INFO FLW-....\] Clock .* slack (\S+)",
                      logPath+"/5_1_fastroute.log")

    extractTagFromFile("globalroute__timing__clock__period", metrics_dict,
                      "^\[INFO FLW-....\] Clock .* period (\S+)",
                      logPath+"/5_1_fastroute.log")

    extractGnuTime("globalroute", metrics_dict, logPath+"/5_1_fastroute.log")

    extractTagFromFile("detailedroute__route__wirelength", metrics_dict,
                       "total wire length = +(\S+) um",
                       logPath+"/5_2_TritonRoute.log")

    extractTagFromFile("detailedroute__route__via__count", metrics_dict,
                       "total number of vias = +(\S+)",
                       logPath+"/5_2_TritonRoute.log")

    extractTagFromFile("detailedroute__route__drc_errors__count", metrics_dict,
                       "(?i)violation",
                       rptPath+"/5_route_drc.rpt",
                       count=True, defaultNotFound=0)

    extractGnuTime("detailedroute", metrics_dict, logPath+"/5_2_TritonRoute.log")

# Finish
# ==============================================================================

    extractTagFromFile("finish__power__internal__total", metrics_dict,
                       "Total +(\S+) +\S+ +\S+ +\S+ +\S+",
                       logPath+"/6_report.log")

    extractTagFromFile("finish__power__switch__total", metrics_dict,
                       "Total +\S+ +(\S+) +\S+ +\S+ +\S+",
                       logPath+"/6_report.log")

    extractTagFromFile("finish__power__leakage__total", metrics_dict,
                       "Total +\S+ +\S+ +(\S+) +\S+ +\S+",
                       logPath+"/6_report.log")

    extractTagFromFile("finish__power__total", metrics_dict,
                       "Total +\S+ +\S+ +\S+ +(\S+) +\S+",
                       logPath+"/6_report.log")

    extractTagFromFile("finish__design__instance__area", metrics_dict,
                      "^Design area (\S+) u\^2",
                       logPath+"/6_report.log")

    extractTagFromFile("finish__design__instance__utilization", metrics_dict,
                      "^Design area.* (\S+)% utilization",
                       logPath+"/6_report.log")

    extractGnuTime("finish", metrics_dict, logPath+"/6_report.log")

# Accumulate time
# ==============================================================================

    failed = False
    total = timedelta()
    for key in metrics_dict:
      if key.endswith("__runtime__total"):
        # Big try block because Hour and microsecond is optional
        try:
          t = datetime.strptime(metrics_dict[key],"%H:%M:%S.%f")
        except ValueError:
          try:
            t = datetime.strptime(metrics_dict[key],"%M:%S.%f")
          except ValueError:
            try:
              t = datetime.strptime(metrics_dict[key],"%H:%M:%S")
            except ValueError:
              try:
                t = datetime.strptime(metrics_dict[key],"%M:%S")
              except ValueError:
                failed = True
                break

        delta = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)
        total += delta

    if failed:
      metrics_dict["total_time"] = "ERR"
    else:
      metrics_dict["total_time"] = str(total)

    with open(output, "w") as resultSpecfile:
        json.dump(metrics_dict, resultSpecfile, indent=2)

    metrics_df = pd.DataFrame(list(metrics_dict.items()))
    col_index = metrics_df.iloc[0][1] + "__" + metrics_df.iloc[1][1]
    metrics_df.columns = ["Metrics", col_index]

    return metrics_dict, metrics_df


args = parse_args()
now = datetime.now()

if args.design == "all_designs":
    print("List of designs")
    rootdir = './logs'

    all_metrics_df = pd.DataFrame()
    all_metrics = []
    flow_variants = args.flowVariant.split()

    cwd = os.getcwd()
    for platform_it in os.scandir(rootdir):
        if platform_it.is_dir():
            plt = platform_it.name
            for design_it in os.scandir(platform_it.path):
                if design_it.is_dir():
                    for variant in flow_variants:
                        des = design_it.name
                        print(plt, des, variant)
                        design_metrics, design_metrics_df = extract_metrics(cwd, plt, des, variant,
                                        os.path.join(".", "reports", plt, des, variant, "metrics.json"))
                        all_metrics.append(design_metrics)
                        if all_metrics_df.shape[0] == 0:
                            all_metrics_df = design_metrics_df
                        else:
                            all_metrics_df = all_metrics_df.merge(design_metrics_df,
                                                    on = 'Metrics', how = 'inner')
#
# render to json and html
#
    with open("metrics.json", "w") as outFile:
        json.dump(all_metrics, outFile)
    metrics_html = all_metrics_df.to_html()
    metrics_html_file = open("metrics.html", "w")
    metrics_html_file.write(metrics_html)
    metrics_html_file.close()
else:
    metrics_dict, metrics_df = extract_metrics(args.flowPath, args.platform, args.design, args.flowVariant, args.output)
