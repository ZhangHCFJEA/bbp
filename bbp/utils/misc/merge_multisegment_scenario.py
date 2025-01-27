#!/usr/bin/env python
"""
Copyright 2010-2019 University Of Southern California

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

 http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Multisegment tool for merging multiple BBP runs into a combined simulation
"""
from __future__ import division, print_function

# Import Python modules
import os
import sys
import glob
import shutil
import argparse

# Import Broadband modules
import seqnum
import bband_utils
from install_cfg import InstallCfg
from station_list import StationList

# Import BBP workflow modules
import plot_srf
import plot_rotd50
from plot_seis import PlotSeis
from rotd100 import RotD100

class MergeScenario(object):
    """
    Implements merging a number of individual simulations into a combined
    BBP run. Useful for combining simulation results from individualy computed
    fault segments into a multi-segment fault
    """

    def __init__(self):
        """
        Initialize class structures
        """
        self.install = InstallCfg.getInstance()
        self.output_sim_id = None
        self.a_indir = None
        self.a_outdir = None
        self.a_logdir = None
        self.a_tmpdir = None
        self.station_list = None
        self.input_sims = []
        self.src_files = []
        self.srf_files = []
        self.scenario = None

    def parse_arguments(self):
        """
        This function takes care of parsing the command-line arguments and
        asking the user for any missing parameters that we need
        """
        parser = argparse.ArgumentParser(description="Processes a numer of "
                                         "single segment BBP runs and combines "
                                         "them into a merged run.")
        parser.add_argument("--sim-id", dest="sim_id", type=int,
                            help="sim_id for merged simulation")
        parser.add_argument("--scenario", dest="scenario",
                            help="scenario name")
        parser.add_argument('input_sims', nargs='*')
        args = parser.parse_args()

        # Input simulations
        if len(args.input_sims) < 2:
            print("[ERROR]: Please provide at least two simulations to merge!")
            sys.exit(-1)

        self.input_sims = args.input_sims

        # Output simulation id
        if args.sim_id is None:
            self.output_sim_id = int(seqnum.get_seq_num())
        else:
            self.output_sim_id = args.sim_id

        # Scenario name
        if args.scenario is None:
            print("[ERROR]: Please provide a scenario name!")
            sys.exit(-1)

        self.scenario = args.scenario

    def create_merged_dirs(self):
        """
        Creates the directory struction for the merged simulation
        """
        install = self.install

        self.a_indir = os.path.join(install.A_IN_DATA_DIR,
                                    str(self.output_sim_id))
        self.a_tmpdir = os.path.join(install.A_TMP_DATA_DIR,
                                     str(self.output_sim_id))
        self.a_outdir = os.path.join(install.A_OUT_DATA_DIR,
                                     str(self.output_sim_id))
        self.a_logdir = os.path.join(install.A_OUT_LOG_DIR,
                                     str(self.output_sim_id))

        # Make sure directories exist
        bband_utils.mkdirs([self.a_tmpdir, self.a_indir,
                            self.a_outdir, self.a_logdir],
                           print_cmd=False)

    def copy_indata_files(self):
        """
        Copies all needed indata files to the new indata directory
        """
        for sim_id in self.input_sims:
            input_dir = os.path.join(self.install.A_IN_DATA_DIR,
                                     str(sim_id))
            # SRC files
            src_file = glob.glob("%s/*.src" % (input_dir))
            if len(src_file) != 1:
                print("[ERROR]: Can't find single SRC file in %s" % (input_dir))
                sys.exit(1)
            src_file = src_file[0]
            self.src_files.append(src_file)
            # SRF files
            in_srf_file = "%s.srf" % (os.path.splitext(src_file)[0])
            tmp_srf_file = os.path.join(self.a_tmpdir,
                                        os.path.basename(in_srf_file))
            self.srf_files.append(tmp_srf_file)
            # Copy files
            shutil.copy2(src_file, self.a_indir)
            shutil.copy2(in_srf_file, self.a_tmpdir)
            shutil.copy2(in_srf_file, self.a_indir)

        # Now copy station list
        input_dir = os.path.join(self.install.A_IN_DATA_DIR,
                                 str(self.input_sims[0]))
        station_file = glob.glob("%s/*.stl" % (input_dir))
        if len(station_file) != 1:
            print("[ERROR]: Can't find station list file in %s" % (input_dir))
            sys.exit(1)
        station_file = station_file[0]
        self.station_list = station_file
        shutil.copy2(station_file, self.a_indir)

        # Copy corrections file if needed
        correction_file = glob.glob("%s/*corrections.txt" % (input_dir))
        if len(correction_file) == 1:
            correction_file = correction_file[0]
            shutil.copy2(correction_file, self.a_indir)

    def add_bbp_seismograms(self, input_files, output_file):
        """
        Add all input files and write output_file with the combined data
        """
        # Start empty
        headers = []
        times = []
        ns_comp = []
        ew_comp = []
        ud_comp = []

        # Read first file
        input_file = input_files[0]
        input_files = input_files[1:]
        i_file = open(input_file, 'r')
        for line in i_file:
            line = line.strip()
            # Empty lines
            if not line:
                continue
            if line.startswith('#') or line.startswith('%'):
                headers.append(line)
                continue
            pieces = line.split()
            pieces = [float(piece) for piece in pieces]
            times.append(pieces[0])
            ns_comp.append(pieces[1])
            ew_comp.append(pieces[2])
            ud_comp.append(pieces[3])
        i_file.close()

        # Now add other files
        for input_file in input_files:
            index = 0
            i_file = open(input_file, 'r')
            for line in i_file:
                line = line.strip()
                # Empty lines
                if not line:
                    continue
                if line.startswith('#') or line.startswith('%'):
                    continue
                pieces = line.split()
                pieces = [float(piece) for piece in pieces]
                if index > len(times):
                    print("[ERROR]: File size mismatch!")
                    sys.exit(1)
                ns_comp[index] = ns_comp[index] + pieces[1]
                ew_comp[index] = ew_comp[index] + pieces[2]
                ud_comp[index] = ud_comp[index] + pieces[3]
                index = index + 1
            i_file.close()

        # Finally write output file
        o_file = open(output_file, 'w')
        for header_line in headers:
            o_file.write("%s\n" % (header_line))
        for time, ns_val, ew_val, ud_val in zip(times, ns_comp,
                                                ew_comp, ud_comp):
            o_file.write("%5.7f   %5.9e   %5.9e    %5.9e\n" %
                         (time, ns_val, ew_val, ud_val))
        o_file.close()

    def merge_seismograms(self):
        """
        Adds seismograms from multiple simulations, creating a set
        of merged seismograms
        """
        # Load station list
        slo = StationList(self.station_list)
        site_list = slo.getStationList()

        # Merge each station
        for station in site_list:
            print("==> Merging station: %s" % (station.scode))
            # Merge both velocity and acceleration
            for file_type in ['vel', 'acc']:
                input_files = []
                for sim_id in self.input_sims:
                    input_dir = os.path.join(self.install.A_OUT_DATA_DIR,
                                             str(sim_id))
                    input_file = os.path.join(input_dir,
                                              "%s.%s.%s.bbp" %
                                              (str(sim_id),
                                               station.scode,
                                               file_type))
                    input_files.append(input_file)
                output_file = os.path.join(self.a_outdir,
                                           "%s.%s.%s.bbp" %
                                           (str(self.output_sim_id),
                                            station.scode,
                                            file_type))
                self.add_bbp_seismograms(input_files, output_file)

    def plot_srf(self):
        """
        Creates the multi-segment SRF plot
        """
        # Save current directory
        old_cwd = os.getcwd()
        os.chdir(self.a_tmpdir)

        for srf_file in self.srf_files:
            srf_file = os.path.basename(srf_file)
            # Write slip file
            srfbase = srf_file[0:srf_file.find(".srf")]
            slipfile = "%s.slip" % (srfbase)
            cmd = ("%s calc_xy=0 type=slip nseg=-1 < %s > %s" %
                   (os.path.join(self.install.A_GP_BIN_DIR, "srf2xyz"),
                    os.path.join(self.a_indir, srf_file),
                    slipfile))
            bband_utils.runprog(cmd)

            # Write tinit file
            tinitfile = "%s.tinit" % (srfbase)
            cmd = ("%s calc_xy=0 type=tinit nseg=-1 < %s > %s" %
                   (os.path.join(self.install.A_GP_BIN_DIR, "srf2xyz"),
                    os.path.join(self.a_indir, srf_file),
                    tinitfile))
            bband_utils.runprog(cmd)

        plottitle = 'Rupture Model for %s' % (self.scenario)
        plot_srf.plot_multi_srf_files(plottitle,
                                      self.srf_files,
                                      self.a_outdir)

        # Restore directory
        os.chdir(old_cwd)

    def post_process(self):
        """
        Run the standard BBP post-processing tasks
        """
        # Plot seismograms
        plotter = PlotSeis(os.path.basename(self.station_list),
                           os.path.basename(self.src_files[0]),
                           True, True, self.output_sim_id)
        plotter.run()
        # RotD50
        process = RotD100(os.path.basename(self.station_list),
                          sim_id=self.output_sim_id)
        process.run()
        # Plot RotD50

        # Load station list
        slo = StationList(self.station_list)
        site_list = slo.getStationList()

        for site in site_list:
            stat = site.scode
            rd50_file = "%d.%s.rd50" % (self.output_sim_id, stat)
            rd50_filename1 = os.path.join(self.a_outdir, rd50_file)
            outfile = os.path.join(self.a_outdir, "%s_%d_%s_rotd50.png" %
                                   (self.scenario, self.output_sim_id, stat))
            plot_rotd50.plot_rd50(stat, rd50_filename1, "-",
                                  self.scenario, "-", outfile,
                                  site.low_freq_corner,
                                  site.high_freq_corner,
                                  quiet=True)

    def merge_multisegment_scenario(self):
        """
        Merges multiple BBP runs for separate fault segments
        into a single simulation
        """
        # Start parsing command-line
        self.parse_arguments()
        print(" BBP Multi-segment Merging Tool ".center(80, '-'))
        # Create new directories
        self.create_merged_dirs()
        # Copy indata files
        self.copy_indata_files()
        # Merge seismograms
        self.merge_seismograms()
        # Plot combined SRF plot
        self.plot_srf()
        # Post-processing steps
        self.post_process()
        print(" BBP Multi-segment Merging Tool Completed ".center(80, '-'))

if __name__ == "__main__":
    ME = MergeScenario()
    ME.merge_multisegment_scenario()
    sys.exit(0)
