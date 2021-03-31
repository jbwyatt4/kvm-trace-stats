#!/usr/bin/python3

# TODO:
#  - system-wide metrics
#  - arbitrary groups of processes metrics (kernel threads,
#    middleware, etc)
#  - parallel scrape
#  - filter by name, not just PID

import subprocess
import operator
import datetime
import threading
import time
import os
import sys
import argparse
import shutil
from datetime import datetime


def mixrange(s):
    r = []
    for i in s.split(","):
        if "-" not in i:
            r.append(int(i))
        else:
            l, h = map(int, i.split("-"))
            r += range(l, h + 1)
    return r


class QemuThread:
    def __init__(self, vm_pid, thread_pid, machine, vhost=False):
        self.vm_pid = vm_pid
        self.machine = machine
        self.thread_pid = thread_pid
        self.last_stealtime = None
        self.last_cputime = None
        self.last_scrape_ts = None
        self.nodes = None
        self.vhost = vhost
        self.pc_steal = 0.0
        self.pc_util = 0.0
        self.diff_steal = 0
        self.diff_util = 0
        self.diff_ts = 0
        self.get_thread_name()
        self.get_thread_cpuset()
        self.get_schedstats()

    def get_thread_name(self):
        if self.vhost is True:
            fpath = '/proc/%s/comm' % (self.thread_pid)
        else:
            fpath = '/proc/%s/task/%s/comm' % (self.vm_pid, self.thread_pid)
        with open(fpath, 'r') as f:
            self.thread_name = f.read().strip()

    def get_thread_cpuset(self):
        if self.vhost is True:
            fpath = '/proc/%s/cpuset' % (self.thread_pid)
        else:
            fpath = '/proc/%s/task/%s/cpuset' % (self.vm_pid, self.thread_pid)
        with open(fpath, 'r') as f:
            self.cpuset = f.read().strip()
        self.nodes = self.machine.get_nodes(self.cpuset)
        if len(self.nodes) > 1:
            # kvm-pit is not pinned, but also mostly idle, no need to
            # warn here
            if 'kvm-pit' in self.thread_name:
                return
            print("Warning: VCPU %d from VM %d belongs to multiple nodes, "
                  "node accounting may be inaccurate" % (self.thread_pid,
                      self.vm_pid))

    def get_schedstats(self):
        self.last_scrape_ts = time.time() * 1000000000
        if self.vhost is True:
            fpath = '/proc/%s/schedstat' % (self.thread_pid)
        else:
            fpath = '/proc/%s/task/%s/schedstat' % (self.vm_pid, self.thread_pid)
        try:
            with open(fpath, 'r') as f:
                stats = f.read().split(' ')
        except FileNotFoundError:
            # On VM teardown return 0
            self.last_cputime = 0
            self.last_stealtime = 0
            return
        self.last_cputime = int(stats[0])
        self.last_stealtime = int(stats[1])

    def __repr__(self):
        return "%s (%s), util: %0.02f %%, steal: %0.02f %%" % (
                self.thread_name, self.thread_pid, self.pc_util,
                self.pc_steal)

    def refresh_stats(self):
        prev_steal_time = self.last_stealtime
        prev_cpu_time = self.last_cputime
        prev_scrape_ts = self.last_scrape_ts
        self.get_schedstats()
        self.diff_ts = self.last_scrape_ts - prev_scrape_ts
        self.diff_steal = self.last_stealtime - prev_steal_time
        self.diff_util = self.last_cputime - prev_cpu_time
        self.pc_util = self.diff_util / self.diff_ts * 100
        self.pc_steal = self.diff_steal / self.diff_ts * 100


class NIC:
    def __init__(self, vm, name):
        self.vm = vm
        self.name = name
        self.last_scrape_ts = None
        self.last_rx = None
        self.last_tx = None
        self.tx_rate = None
        self.rx_rate = None
        self.get_stats()

    def get_stats(self):
        self.last_scrape_ts = time.time()
        # Flipped rx/tx to reflect the VM point of view
        try:
            with open('/sys/devices/virtual/net/%s/statistics/tx_bytes' %
                      self.name, 'r') as f:
                self.last_rx = int(f.read().strip())
            with open('/sys/devices/virtual/net/%s/statistics/rx_bytes' %
                      self.name, 'r') as f:
                self.last_tx = int(f.read().strip())
        except:
            # VM Teardown
            self.last_rx = 0
            self.last_tx = 0
            return

    def refresh_stats(self):
        prev_scrape_ts = self.last_scrape_ts
        prev_rx = self.last_rx
        prev_tx = self.last_tx
        self.get_stats()
        diff_sec = self.last_scrape_ts - prev_scrape_ts
        mb = 1024.0 * 1024.0
        self.rx_rate = (self.last_rx - prev_rx) / diff_sec / mb
        self.tx_rate = (self.last_tx - prev_tx) / diff_sec / mb


class VM:
    def __init__(self, args, vm_pid, machine):
        self.args = args
        self.vm_pid = vm_pid
        self.machine = machine
        self.name = None
        self.csv = None
        self.mem_allocated = 0

        # We assume all the allocated memory was allocated to fit on
        # only one node, we still track the real usage on each node.
        # changes protected by machine.nodes_lock.
        self.primary_node = None
        # If a VM changed node, store it here and update with
        # machine.nodes_lock is held by the vm allocation thread
        self.new_primary_node = None

        self.mem_used_per_node = {}
        self.total_vcpu_count = 0
        self.total_vcpu_count_per_node = {}

        self.vcpu_threads = {}
        self.emulator_threads = {}
        self.vhost_threads = {}
        self.nics = {}

        self.last_io_scrape_ts = None
        self.last_io_read_bytes = None
        self.last_io_write_bytes = None

        self.get_vm_info()
        if self.args.csv is not None and self.args.vm is True:
            self.open_vm_csv()
        self.get_threads()
        self.get_node_memory()
        self.get_nic_info()
        self.refresh_io_stats()

    def __str__(self):
        if self.args.vcpu:
            vm = "  - %s (%s), vcpu util: %0.02f%%, vcpu steal: %0.02f%%, " \
                    "vhost util: %0.02f%%, vhost steal: %0.02f%%" \
                 "emulators util: %0.02f%%, emulators steal: %0.02f%%" % (
                    self.name, self.vm_pid,
                    self.vcpu_sum_pc_util,
                    self.vcpu_sum_pc_steal,
                    self.vhost_sum_pc_util,
                    self.vhost_sum_pc_steal,
                    self.emulators_sum_pc_util,
                    self.emulators_sum_pc_steal)
            vcpu_util = ""
            for v in self.vcpu_threads.values():
                vcpu_util = "%s\n    - %s" % (vcpu_util, v)
            emulators_util = ""
            if self.args.emulators:
                for v in self.emulator_threads.values():
                    emulators_util = "%s\n    - %s" % (emulators_util, v)
            return "%s%s%s" % (vm, vcpu_util, emulators_util)
        else:
            return self.args.vm_format.format(
                    self.name, str(self.vm_pid),
                    "%0.02f %%" % self.vcpu_sum_pc_util,
                    "%0.02f %%" % self.vcpu_sum_pc_steal,
                    "%0.02f %%" % self.vhost_sum_pc_util,
                    "%0.02f %%" % self.vhost_sum_pc_steal,
                    "%0.02f %%" % self.emulators_sum_pc_util,
                    "%0.02f %%" % self.emulators_sum_pc_steal,
                    "%0.02f MB/s" % self.mb_read,
                    "%0.02f MB/s" % self.mb_write,
                    "%0.02f MB/s" % self.rx_rate,
                    "%0.02f MB/s" % self.tx_rate)

    def open_vm_csv(self):
        fname = os.path.join(self.args.csv, "%s.csv" % self.name)
        self.csv = open(fname, 'w')
        self.csv.write("timestamp,pid,name,node,vcpu_util,vcpu_steal,emulators_util,"
                "emulators_steal,vhost_util,vhost_steal,disk_read,disk_write,rx,tx\n")

    def output_vm_csv(self, timestamp):
        # Output the CSV file
        # we use abs() because Python manages to write -0.00 once in a
        # while...
        self.csv.write(f"{datetime.fromtimestamp(timestamp)},"
                       f"{self.vm_pid},{self.name},"
                       f"{self.primary_node.id},"
                       f"{'%0.02f' % (abs(self.vcpu_sum_pc_util))},"
                       f"{'%0.02f' % (abs(self.vcpu_sum_pc_steal))},"
                       f"{'%0.02f' % (abs(self.emulators_sum_pc_util))},"
                       f"{'%0.02f' % (abs(self.emulators_sum_pc_steal))},"
                       f"{'%0.02f' % (abs(self.vhost_sum_pc_util))},"
                       f"{'%0.02f' % (abs(self.vhost_sum_pc_steal))},"
                       f"{'%0.02f' % (abs(self.mb_read))},"
                       f"{'%0.02f' % (abs(self.mb_write))},"
                       f"{'%0.02f' % (abs(self.rx_rate))},"
                       f"{'%0.02f' % (abs(self.tx_rate))}\n")

    def get_nic_info(self):
        cmd = ['virsh', 'domiflist', self.name]
        lines = subprocess.check_output(
                cmd, shell=False).strip().decode("utf-8").split('\n')
        for l in lines:
            fields = l.split()
            if len(fields) == 1:
                continue
            if fields[0] == 'Interface':
                continue
            self.nics[fields[0]] = NIC(self, fields[0])

    def get_threads(self):
        for tid in os.listdir('/proc/%s/task/' % self.vm_pid):
            fname = '/proc/%s/task/%s/comm' % (self.vm_pid, tid)
            try:
                with open(fname, 'r') as _f:
                    comm = _f.read()
                tid = int(tid)
                thread = QemuThread(self.vm_pid, tid, self.machine)
            except:
                # Ignore threads that disappear for now (temporary workers)
                continue
            if 'CPU' in comm:
                self.vcpu_threads[tid] = thread
            else:
                self.emulator_threads[tid] = thread

        # Find vhost threads
        cmd = ["pgrep", str(self.vm_pid)]
        pids = subprocess.check_output(
                cmd, shell=False).strip().decode("utf-8").split('\n')
        for p in pids:
            tid = int(p)
            thread = QemuThread(self.vm_pid, tid, self.machine, vhost=True)
            self.vhost_threads[tid] = thread

    def get_vm_info(self):
        with open('/proc/%s/cmdline' % self.vm_pid, mode='r') as fh:
            cmdline = fh.read().split('\0')
        for i in range(len(cmdline)):
            if cmdline[i].startswith('guest='):
                self.name = cmdline[i].split('=')[1].split(',')[0]
            if cmdline[i] == '-m':
                self.mem_allocated = int(cmdline[i+1])
            if cmdline[i] == '-smp':
                self.total_vcpu_count = int(cmdline[i+1].split(',')[0])

    def refresh_io_stats(self):
        self.last_io_scrape_ts = time.time()
        try:
            with open('/proc/%s/io' % self.vm_pid, 'r') as f:
                stats = f.read().split('\n')
        except FileNotFoundError:
            # On VM teardown return 0
            self.last_io_read_bytes = 0
            self.last_io_write_bytes = 0
            return

        for l in stats:
            l = l.split(' ')
            if l[0] == 'read_bytes:':
                self.last_io_read_bytes = int(l[1])
            if l[0] == 'write_bytes:':
                self.last_io_write_bytes = int(l[1])

    def get_node_memory(self):
        cmd = ["numastat", "-p", str(self.vm_pid)]
        try:
            usage = subprocess.check_output(
                    cmd,
                    shell=False).decode("utf-8").split('\n')[-2].split()[1:-1]
        except subprocess.CalledProcessError:
            # ctrl-c
            return
        maxnode = None
        maxmem = 0
        for node_id in range(len(usage)):
            try:
                mem = float(usage[node_id])
            except ValueError:
                # Teardown
                return
            self.mem_used_per_node[node_id] = mem
            self.machine.nodes[node_id].vm_mem_used += mem
            if maxnode is None or mem > maxmem:
                maxnode = node_id
                maxmem = mem

        if self.primary_node is None:
            self.primary_node = self.machine.nodes[maxnode]
        elif self.primary_node != self.machine.nodes[maxnode]:
            self.new_primary_node = self.machine.nodes[maxnode]
        self.primary_node.vm_mem_allocated += self.mem_allocated

    def refresh_stats(self):
        # FIXME: this is too heavy to run at each loop, but we would need
        # it to track VMs that move between nodes
#        self.get_node_memory()
        # sum of all vcpu stats
        self.vcpu_sum_pc_util = 0
        self.vcpu_sum_pc_steal = 0
        for vcpu in self.vcpu_threads.values():
            vcpu.refresh_stats()
            self.vcpu_sum_pc_util += vcpu.pc_util
            self.vcpu_sum_pc_steal += vcpu.pc_steal

        # vhost
        self.vhost_sum_pc_util = 0
        self.vhost_sum_pc_steal = 0
        for vhost in self.vhost_threads.values():
            vhost.refresh_stats()
            self.vhost_sum_pc_util += vhost.pc_util
            self.vhost_sum_pc_steal += vhost.pc_steal

        # emulators
        self.emulators_sum_pc_util = 0
        self.emulators_sum_pc_steal = 0
        to_remove = []
        for emulator in self.emulator_threads.values():
            try:
                emulator.refresh_stats()
            except Exception:
                to_remove.append(emulator)
                continue
            self.emulators_sum_pc_util += emulator.pc_util
            self.emulators_sum_pc_steal += emulator.pc_steal
        # workers are added/removed on demand, so we can't keep track of all
        # FIXME
#        for r in to_remove:
#            del emulators

        # disk
        prev_io_scrape_ts = self.last_io_scrape_ts
        prev_io_read_bytes = self.last_io_read_bytes
        prev_io_write_bytes = self.last_io_write_bytes
        self.refresh_io_stats()
        diff_sec = self.last_io_scrape_ts - prev_io_scrape_ts
        mb = 1024.0*1024.0
        self.mb_read = (self.last_io_read_bytes - prev_io_read_bytes) / diff_sec / mb
        self.mb_write = (self.last_io_write_bytes - prev_io_write_bytes) / diff_sec / mb

        self.tx_rate = 0
        self.rx_rate = 0
        for n in self.nics.values():
            n.refresh_stats()
            self.tx_rate += n.tx_rate
            self.rx_rate += n.rx_rate

        # copy to node stats
        self.primary_node.vcpu_sum_pc_util += self.vcpu_sum_pc_util
        self.primary_node.vcpu_sum_pc_steal += self.vcpu_sum_pc_steal
        self.primary_node.vhost_sum_pc_util += self.vhost_sum_pc_util
        self.primary_node.vhost_sum_pc_steal += self.vhost_sum_pc_steal
        self.primary_node.emulators_sum_pc_util += self.emulators_sum_pc_util
        self.primary_node.emulators_sum_pc_steal += self.emulators_sum_pc_steal


class Node:
    def __init__(self, _id, args):
        self.id = _id
        self.args = args
        self.hwthread_list = []
        # Approximation, VMs could be split between nodes, we use the node
        # where most of the memory is allocated to decide here
        self.node_vms = {}

        # After the initial scan, the resource accounting is owned by the
        # refresh_vm_allocation thread
        # Approximation, assumes all the allocated memory is not split
        self.vm_mem_allocated = 0
        self.vm_mem_used = 0
        self.node_vcpu_threads = 0

        self.clear_stats()

    def clear_stats(self):
        # Owned by the main loop
        self.vcpu_sum_pc_util = 0
        self.vcpu_sum_pc_steal = 0
        self.vhost_sum_pc_util = 0
        self.vhost_sum_pc_steal = 0
        self.emulators_sum_pc_util = 0
        self.emulators_sum_pc_steal = 0

    def refresh_vm_allocation(self):
        self.vm_mem_allocated = 0
        self.vm_mem_used = 0
        self.node_vcpu_threads = 0
        for vm in self.node_vms.values():
            vm.get_node_memory()

    def print_node_initial_count(self):
        if self.args.csv is not None:
            return
        return("%s VMs (%s vcpus, %0.02f GB mem allocated, "
              "%0.02f GB mem used)" % (
                self.nr_vms, self.node_vcpu_threads,
                self.vm_mem_allocated/1024, self.vm_mem_used/1024))

    def open_csv_file(self):
        fname = os.path.join(self.args.csv, 'node%d.csv' % self.id)
        print("Writing node %s data in %s" % (self.id, fname))
        self.node_csv = open(fname, 'w')
        self.node_csv.write("timestamp,id,nr_vms,nr_vcpus,vm_mem_allocated,"
                            "vm_mem_used,vcpu_util,vcpu_steal,emulators_util,"
                            "emulators_steal,vhost_util,vhost_steal\n")

    def output_node_csv(self, timestamp):
        self.node_csv.write(f"{datetime.fromtimestamp(timestamp)},"
                            f"{self.id},"
                            f"{self.nr_vms},"
                            f"{self.node_vcpu_threads},"
                            f"{self.vm_mem_allocated/1024},"
                            f"{self.vm_mem_used/1024},"
                            f"{'%0.02f' % (self.vcpu_sum_pc_util / self.nr_hwthreads)},"
                            f"{'%0.02f' % (self.vcpu_sum_pc_steal / self.nr_hwthreads)},"
                            f"{'%0.02f' % (self.emulators_sum_pc_util / self.nr_hwthreads)},"
                            f"{'%0.02f' % (self.emulators_sum_pc_steal / self.nr_hwthreads)},"
                            f"{'%0.02f' % (self.vhost_sum_pc_util / self.nr_hwthreads)},"
                            f"{'%0.02f' % (self.vhost_sum_pc_steal / self.nr_hwthreads)}\n")

    def output_allocation(self):
        print("  Node %d: %s" % (self.id, self.print_node_initial_count()))

    @property
    def nr_vms(self):
        return len(self.node_vms)

    @property
    def nr_hwthreads(self):
        return len(self.hwthread_list)


class Machine:
    def __init__(self, args):
        self.args = args

        # to read/update node_vms in each node, prevents concurrent
        # accesses by the main loop and the vm_allocation thread
        self.nodes_lock = threading.Lock()

        self.nodes = {}
        self.all_vms = {}
        self.get_cpuset_mount_point()
        self.cancel = False

    def get_cpuset_mount_point(self):
        with open('/proc/mounts', 'r') as f:
            mounts = f.read().split('\n')
        for m in mounts:
            m = m.split()
            if m[0] == 'cgroup':
                if 'cpuset' in m[3]:
                    self.cpuset_mount_point = m[1]
                    return

    def refresh_stats(self):
        for node in self.nodes.values():
            node.clear_stats()
        for vm in self.all_vms.values():
            vm.refresh_stats()

    def account_vcpus(self):
        for vm in self.all_vms.values():
            vm.primary_node.node_vcpu_threads += len(vm.vcpu_threads.keys())

    def refresh_vm_allocation(self):
        while True:
            # Sleep 1s between scans
            for i in range(10):
                if self.cancel is True:
                    return
                time.sleep(0.1)
            self.list_vms()
            for vm in self.all_vms.values():
                # If a VM switched node
                if vm.new_primary_node is not None:
                    try:
                        self.nodes_lock.acquire()
                        del vm.primary_node.node_vms[vm.vm_pid]
                        vm.primary_node.vm_mem_allocated -= vm.mem_allocated

                        vm.new_primary_node.node_vms[vm.vm_pid] = vm
                        vm.new_primary_node.vm_mem_allocated += vm.mem_allocated
                        vm.primary_node = vm.new_primary_node
                        vm.new_primary_node = None
                    finally:
                        self.nodes_lock.release()
            for node in self.nodes.values():
                node.node_vcpu_threads = 0
                if self.cancel is True:
                    return
                node.refresh_vm_allocation()
            self.account_vcpus()

    def print_initial_count(self):
        for node in self.nodes.values():
            self.print_node_count(node.id)

    def print_node_count(self, node_id):
        node = self.nodes[node_id]
        node.output_allocation()

    def get_nodes(self, cpuset):
        nodes = []
        fullpath = "%s/%s/cpuset.cpus" % (self.cpuset_mount_point, cpuset)
        with open(fullpath, 'r') as f:
            cpus = mixrange(f.read())
        for c in cpus:
            for n in self.nodes.values():
                if c in n.hwthread_list:
                    if n not in nodes:
                        nodes.append(n)
                    break
        return nodes

    @property
    def nr_nodes(self):
        return len(self.nodes)

    @property
    def nr_hwthreads(self):
        nr = 0
        for n in self.nodes.values():
            nr += len(n.hwthread_list)
        return nr

    def get_info(self):
        cmd = "lscpu | egrep 'NUMA node[0-9]+ CPU'"
        numa_info = subprocess.check_output(
                cmd, shell=True).strip().decode("utf-8")
        for i in numa_info.split("\n"):
            node_id = int(i.split(' ')[1].replace('node', ''))
            node = Node(node_id, self.args)
            hwthreads = i.split(':')[1].replace(' ', '')
            _i = mixrange(hwthreads)
            for j in _i:
                node.hwthread_list.append(int(j))
            self.nodes[node_id] = node

    def del_vm(self, pid):
        v = self.all_vms[pid]
        del v.primary_node.node_vms[pid]
        del self.all_vms[pid]


    def list_vms(self):
        cmd = ["pgrep", "qemu"]
        try:
            pids = subprocess.check_output(
                    cmd, shell=False).strip().decode("utf-8").split('\n')
        except subprocess.CalledProcessError:
            l = list(self.all_vms.keys())
            for v in l:
                self.del_vm(v)
            return
        except KeyboardInterrupt:
            return
        # to track the VMs that have disappeared since the last scan
        previous_vm_list = list(self.all_vms.keys())
        for pid in pids:
            if self.cancel is True:
                return
            pid = int(pid)
            if pid in self.all_vms.keys():
                previous_vm_list.remove(pid)
                continue
            v = VM(self.args, pid, self)
            v.primary_node.node_vms[pid] = v
            self.all_vms[pid] = v

        if len(previous_vm_list) != 0:
            for pid in previous_vm_list:
                self.del_vm(pid)


class VmTop:
    def __init__(self):
        self.parse_args()
        self.machine = Machine(self.args)
        print("Collecting VM informations...")
        self.machine.get_info()
        self.vm_alloc_thread = None
        if self.args.csv is not None:
            self.csv = True
            self.open_csv_files()
        else:
            self.csv = False

        # Initial list and allocation accounting
        self.machine.list_vms()
        self.machine.account_vcpus()
        if self.csv is False:
            self.machine.print_initial_count()

        # Scan for new VMs and memory/vcpu allocation in the background
        self.vm_alloc_thread = threading.Thread(
                target=self.machine.refresh_vm_allocation)
        self.vm_alloc_thread.start()

        # Main loop
        self.loop()

    def parse_args(self):
        parser = argparse.ArgumentParser(description='Monitor local steal')
        parser.add_argument('-r', '--refresh', type=int, default=1,
                            help='refresh rate (seconds)')
        parser.add_argument('-l', '--limit', type=int,
                            help='limit to top X VMs per node')
        parser.add_argument('-s', '--sort', type=str,
                            choices=['vcpu_util', 'vcpu_steal',
                                     'vhost_util', 'vhost_steal',
                                     'disk_read', 'disk_write',
                                     'emulators_util', 'emulators_steal',
                                     'rx', 'tx'],
                            default='vcpu_util',
                            help='sort order for VM list, default: vcpu_util')
        parser.add_argument('-p', '--pid', type=str,
                            help='Limit to pid (csv), implies --vm')
        parser.add_argument('--vcpu', action='store_true',
                            help='show vcpu stats (implies --vm)')
        parser.add_argument('--csv', type=str,
                            help='Output as CSV files in provided folder name')
        parser.add_argument('--emulators', action='store_true',
                            help='show emulators stats (implies --vm)')
        parser.add_argument('--vm', action='store_true',
                            help='show vm stats')
        parser.add_argument('--node', type=str,
                            help='Limit to specific NUMA node (csv)')
        self.args = parser.parse_args()
        if self.args.vcpu is True or self.args.emulators is True:
            self.args.vm = True
        if self.args.pid is not None:
            self.args.vm = True
            self.args.pids = []
            for i in self.args.pid.split(','):
                self.args.pids.append(int(i))
        # Sort mapping to variable name
        if self.args.sort == 'vcpu_util':
            self.args.sort = 'vcpu_sum_pc_util'
        elif self.args.sort == 'vcpu_steal':
            self.args.sort = 'vcpu_sum_pc_steal'
        elif self.args.sort == 'vhost_util':
            self.args.sort = 'vhost_sum_pc_util'
        elif self.args.sort == 'vhost_steal':
            self.args.sort = 'vhost_sum_pc_steal'
        elif self.args.sort == 'emulators_util':
            self.args.sort = 'emulators_sum_pc_util'
        elif self.args.sort == 'emulators_steal':
            self.args.sort = 'emulators_sum_pc_steal'
        elif self.args.sort == 'disk_read':
            self.args.sort = 'mb_read'
        elif self.args.sort == 'disk_write':
            self.args.sort = 'mb_write'
        elif self.args.sort == 'rx':
            self.args.sort = 'rx_rate'
        elif self.args.sort == 'tx':
            self.args.sort = 'tx_rate'

        self.args.vm_format = '{:<19s}{:<8s}{:<12s}{:<12s}{:<12s}{:<12s}{:<10s}{:<10s}{:<13s}{:<13s}{:<13s}{:<13s}'

        # filter by node
        if self.args.node is not None:
            nodes = []
            for n in self.args.node.split(','):
                nodes.append(int(n))
            self.args.node = nodes

    def open_csv_files(self):
        try:
            os.mkdir(self.args.csv)
        except FileExistsError:
            print("Error: folder %s already exists, aborting" % self.args.csv)
            sys.exit(1)
        for n in self.machine.nodes.values():
            n.open_csv_file()
        if self.args.vm is True:
            print("Writing per-VM csv file")
        else:
            print("NOT writing per-VM data")

    def check_diskspace(self):
        # Be nice and abort if disk left is less than 1GB
        if self.args.csv is not None:
            if shutil.disk_usage(self.args.csv)[2] < 1*1024*1024*1024:
                print("Less than 1GB available on disk, exiting")
                self.machine.cancel = True
                sys.exit(1)

    def loop(self):
        while True:
            try:
                time.sleep(self.args.refresh)
            except KeyboardInterrupt:
                if self.vm_alloc_thread is not None:
                    self.machine.cancel = True
                    self.vm_alloc_thread.join()
                return
            self.check_diskspace()
            if not self.vm_alloc_thread.is_alive():
                print("Background allocation thread crashed, exiting")
                sys.exit(1)
            if self.csv is False:
                print("\n%s" % datetime.datetime.today())
            else:
                timestamp = int(time.time())
            self.machine.refresh_stats()

            try:
                # Prevent the list of VMs per node to be updated during
                # the output
                self.machine.nodes_lock.acquire()
                for node in self.machine.nodes.keys():
                    if self.args.node is not None:
                        if node not in self.args.node:
                            continue
                    nr = 0
                    node = self.machine.nodes[node]
                    if self.args.vm and self.csv is False:
                        print("Node %d:" % node.id)
                        if not self.args.vcpu:
                            print(self.args.vm_format.format(
                                "Name", "PID", "vcpu util", "vcpu steal",
                                "vhost util", "vhost steal", "emu util",
                                "emu steal", "disk read", "disk write",
                                "rx", "tx"))
                    for vm in (sorted(node.node_vms.values(),
                                      key=operator.attrgetter(self.args.sort),
                                      reverse=True)):
                        if self.args.vm:
                            if self.args.pid is not None:
                                if vm.vm_pid in self.args.pids:
                                    print(vm)
                            else:
                                if self.args.limit is not None and \
                                        nr >= self.args.limit:
                                    break
                                if self.csv is True:
                                    vm.output_vm_csv(timestamp)
                                else:
                                    print(vm)
                                nr += 1
                    if self.csv:
                        node.output_node_csv(timestamp)
                    else:
                        print("  Node %d: vcpu util: %0.02f%%, "
                              "vcpu steal: %0.02f%%, emulators util: %0.02f%%, "
                              "emulators steal: %0.02f%%" % (
                                  node.id,
                                  node.vcpu_sum_pc_util / node.nr_hwthreads,
                                  node.vcpu_sum_pc_steal / node.nr_hwthreads,
                                  node.emulators_sum_pc_util / node.nr_hwthreads,
                                  node.emulators_sum_pc_steal / node.nr_hwthreads))
                        self.machine.print_node_count(node.id)
            finally:
                self.machine.nodes_lock.release()

    def run(self):
        pass


if os.geteuid() != 0:
    print("Need to run as root")
    sys.exit(1)

s = VmTop()
s.run()
