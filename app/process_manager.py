"""Process manager to track and kill child processes."""

import os
import signal
import psutil
from typing import Set

class ProcessManager:
    def __init__(self):
        self.child_pids: Set[int] = set()
    
    def register_child(self, pid: int):
        """Register a child process to be killed on stop."""
        self.child_pids.add(pid)
    
    def kill_all_children(self):
        """Kill all registered child processes and their descendants."""
        for pid in list(self.child_pids):
            try:
                parent = psutil.Process(pid)
                # Kill all children of this process
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                # Kill the parent
                parent.kill()
                self.child_pids.discard(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.child_pids.discard(pid)
    
    def kill_downloads(self):
        """Kill all yt-dlp and aria2c processes."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name', '')
                cmdline = proc.info.get('cmdline', [])
                cmdline_str = ' '.join(cmdline) if cmdline else ''
                
                # Kill yt-dlp and aria2c processes
                if 'yt-dlp' in name or 'yt-dlp' in cmdline_str or \
                   'aria2c' in name or 'aria2c' in cmdline_str:
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

# Global process manager
_process_manager = ProcessManager()

def get_process_manager():
    return _process_manager