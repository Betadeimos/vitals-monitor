import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import psutil

# Adding the root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import vitals
import vitals_core

class TestOrchestrator(unittest.TestCase):

    @patch('psutil.process_iter')
    @patch('psutil.Process')
    def test_orchestrator_high_ram_behavior(self, mock_process_class, mock_process_iter):
        # 1. Setup Mock Instances
        vip_pid = 1000
        other_pid = 2000
        
        vip_proc = MagicMock()
        vip_proc.pid = vip_pid
        vip_proc.nice.return_value = 32 # Normal
        vip_proc.status.return_value = 'running'
        
        other_proc = MagicMock()
        other_proc.pid = other_pid
        other_proc.nice.return_value = 32
        other_proc.status.return_value = 'running'
        
        active_instances = {
            vip_pid: {'proc': vip_proc, 'status_msg': None},
            other_pid: {'proc': other_proc, 'status_msg': None}
        }
        
        # 2. High RAM case
        vitals.manage_orchestration(active_instances, 85.0, vip_pid)
        
        # Verify VIP elevation
        vip_proc.nice.assert_called_with(psutil.HIGH_PRIORITY_CLASS)
        self.assertEqual(active_instances[vip_pid]['status_msg'], "[ STATUS: VIP - HIGH PRIORITY ]")
        
        # Verify Other suspension
        other_proc.suspend.assert_called_once()
        self.assertEqual(active_instances[other_pid]['status_msg'], "[ STATUS: SUSPENDED TO RECLAIM RAM ]")

    @patch('psutil.process_iter')
    def test_orchestrator_normal_ram_behavior(self, mock_process_iter):
        # 1. Setup Mock Instances (previously elevated/suspended)
        vip_pid = 1000
        other_pid = 2000
        
        vip_proc = MagicMock()
        vip_proc.pid = vip_pid
        vip_proc.nice.return_value = 128 # High
        vip_proc.status.return_value = 'running'
        
        other_proc = MagicMock()
        other_proc.pid = other_pid
        other_proc.nice.return_value = 32
        other_proc.status.return_value = 'stopped' # Stopped
        
        active_instances = {
            vip_pid: {'proc': vip_proc, 'status_msg': "[ STATUS: VIP - HIGH PRIORITY ]"},
            other_pid: {'proc': other_proc, 'status_msg': "[ STATUS: SUSPENDED TO RECLAIM RAM ]"}
        }
        
        # 2. Normal RAM case
        vitals.manage_orchestration(active_instances, 70.0, vip_pid)
        
        # Verify VIP restoration
        vip_proc.nice.assert_called_with(psutil.NORMAL_PRIORITY_CLASS)
        self.assertIsNone(active_instances[vip_pid]['status_msg'])
        
        # Verify Other resumption
        other_proc.resume.assert_called_once()
        self.assertIsNone(active_instances[other_pid]['status_msg'])

    @patch('psutil.Process')
    @patch('psutil.process_iter')
    def test_orchestrator_collateral_hogs(self, mock_process_iter, mock_process_class):
        # Mock chrome and edge
        chrome_proc = MagicMock()
        chrome_proc.info = {'name': 'chrome.exe'}
        chrome_proc.status.return_value = 'running'
        chrome_proc.pid = 3000
        
        # When psutil.Process(3000) is called, return chrome_proc
        mock_process_class.return_value = chrome_proc
        mock_process_iter.return_value = [chrome_proc]
        
        active_instances = {}
        
        # High RAM
        vitals.manage_orchestration(active_instances, 85.0, 0)
        chrome_proc.suspend.assert_called_once()
        
        # Simulate chrome_proc is now stopped
        chrome_proc.status.return_value = 'stopped'
        
        # Low RAM
        vitals.manage_orchestration(active_instances, 70.0, 0)
        chrome_proc.resume.assert_called_once()

if __name__ == '__main__':
    unittest.main()
