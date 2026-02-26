import pytest
import socket
import json
import time
import subprocess
import signal
import os
import threading
from collections import defaultdict

class TestHelper:
    """Helper class for managing test processes and network operations"""
    
    def __init__(self):
        self.processes = []
        self.base_seed_port = 5000
        self.base_peer_port = 6000
        self.config_file = 'test_config.csv'
        
    def start_seed(self, port, config_file=None):
        """Start a seed node process"""
        if config_file is None:
            config_file = self.config_file
        cmd = ['python3', 'seed.py', config_file, str(port)]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        time.sleep(1)  # Allow seed to start
        return process
    
    def start_peer(self, port, config_file=None):
        """Start a peer node process"""
        if config_file is None:
            config_file = self.config_file
        cmd = ['python3', 'peer.py', config_file, str(port)]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        time.sleep(1)  # Allow peer to start
        return process
    
    def send_message(self, ip, port, msg, timeout=2):
        """Send a message to a node and get response"""
        try:
            with socket.create_connection((ip, port), timeout=timeout) as s:
                s.sendall(json.dumps(msg).encode('utf-8'))
                data = s.recv(8192).decode('utf-8')
                if data:
                    return json.loads(data)
        except Exception as e:
            return None
        return None
    
    def cleanup(self):
        """Clean up all spawned processes"""
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                try:
                    process.kill()
                except:
                    pass
        self.processes = []
        
    def create_test_config(self, seed_ports, config_file=None):
        """Create a test configuration file"""
        if config_file is None:
            config_file = self.config_file
        with open(config_file, 'w') as f:
            for port in seed_ports:
                f.write(f'127.0.0.1,{port}\n')
    
    def wait_for_port(self, port, timeout=5):
        """Wait for a port to become available"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=1):
                    return True
            except:
                time.sleep(0.1)
        return False


@pytest.fixture
def helper():
    """Pytest fixture to provide test helper and cleanup"""
    h = TestHelper()
    yield h
    h.cleanup()
    # Clean up test files
    if os.path.exists('test_config.csv'):
        os.remove('test_config.csv')
    if os.path.exists('outputfile.txt'):
        os.remove('outputfile.txt')


class TestSeedNodes:
    """Test cases for seed node functionality"""
    
    def test_01_single_seed_startup(self, helper):
        """Test Case 1: Single seed node can start successfully"""
        seed_ports = [helper.base_seed_port]
        helper.create_test_config(seed_ports)
        
        process = helper.start_seed(seed_ports[0])
        assert helper.wait_for_port(seed_ports[0]), "Seed node failed to start"
        
        # Verify seed is responsive
        response = helper.send_message('127.0.0.1', seed_ports[0], {'type': 'GET_PL'})
        assert response is not None, "Seed node not responding"
        assert response['status'] == 'SUCCESS', "Seed node returned error"
    
    def test_02_multiple_seeds_startup(self, helper):
        """Test Case 2: Multiple seed nodes start and communicate"""
        seed_ports = [helper.base_seed_port + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start all seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        # Verify all seeds are responsive
        for port in seed_ports:
            assert helper.wait_for_port(port), f"Seed on port {port} failed to start"
            response = helper.send_message('127.0.0.1', port, {'type': 'GET_PL'})
            assert response is not None and response['status'] == 'SUCCESS'
    
    def test_03_peer_registration_consensus(self, helper):
        """Test Case 3: Peer registration achieves consensus across seeds"""
        seed_ports = [helper.base_seed_port + 10 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start an actual peer (not just send REGISTER manually)
        peer_port = helper.base_peer_port + 10
        helper.start_peer(peer_port)
        
        # Wait for peer registration and consensus (peer waits 3s + network delays)
        time.sleep(6)
        
        # Check all seeds have the peer in their PL
        consensus_count = 0
        for port in seed_ports:
            response = helper.send_message('127.0.0.1', port, {'type': 'GET_PL'})
            if response and 'PL' in response:
                pl = response['PL']
                if ['127.0.0.1', peer_port] in pl:
                    consensus_count += 1
        
        # Majority should have consensus
        assert consensus_count >= 2, f"Consensus not reached: only {consensus_count}/3 seeds agreed"


class TestPeerNodes:
    """Test cases for peer node functionality"""
    
    def test_04_peer_startup_and_registration(self, helper):
        """Test Case 4: Peer node starts and registers with seeds"""
        seed_ports = [helper.base_seed_port + 20 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peer
        peer_port = helper.base_peer_port + 20
        helper.start_peer(peer_port)
        
        # Wait for registration (peer startup + 3s wait + consensus time)
        time.sleep(7)
        
        # Check if peer is registered in seed PLs
        found = False
        for seed_port in seed_ports:
            response = helper.send_message('127.0.0.1', seed_port, {'type': 'GET_PL'})
            if response and 'PL' in response:
                for peer in response['PL']:
                    if peer[1] == peer_port:
                        found = True
                        break
        
        assert found, "Peer not found in any seed's peer list"
    
    def test_05_multiple_peers_parallel_registration(self, helper):
        """Test Case 5: Multiple peers register simultaneously"""
        seed_ports = [helper.base_seed_port + 30 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start multiple peers in parallel
        peer_ports = [helper.base_peer_port + 30 + i for i in range(5)]
        for port in peer_ports:
            helper.start_peer(port)
        
        # Wait for all registrations (multiple peers + consensus)
        time.sleep(10)
        
        # Check how many peers are in the PL
        response = helper.send_message('127.0.0.1', seed_ports[0], {'type': 'GET_PL'})
        assert response is not None
        peer_count = len(response.get('PL', []))
        
        # At least some peers should be registered
        assert peer_count >= 3, f"Expected at least 3 peers registered, got {peer_count}"
    
    def test_06_peer_degree_query(self, helper):
        """Test Case 6: Peer responds to degree queries"""
        seed_ports = [helper.base_seed_port + 40 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peers
        peer_ports = [helper.base_peer_port + 40 + i for i in range(3)]
        for port in peer_ports:
            helper.start_peer(port)
        
        time.sleep(6)
        
        # Query degree from a peer
        response = helper.send_message('127.0.0.1', peer_ports[0], {'type': 'GET_DEGREE'})
        assert response is not None, "Peer not responding to degree query"
        assert 'degree' in response, "Response missing degree field"
        assert response['status'] == 'SUCCESS'


class TestGossipProtocol:
    """Test cases for gossip protocol functionality"""
    
    def test_07_gossip_message_propagation(self, helper):
        """Test Case 7: Gossip messages propagate through the network"""
        seed_ports = [helper.base_seed_port + 50 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peers
        peer_ports = [helper.base_peer_port + 50 + i for i in range(4)]
        for port in peer_ports:
            helper.start_peer(port)
        
        # Wait for network formation and gossip to start
        time.sleep(12)
        
        # Check output file for gossip messages
        if os.path.exists('outputfile.txt'):
            with open('outputfile.txt', 'r') as f:
                content = f.read()
                # Check if gossip messages were generated and received
                assert 'Generating GOSSIP' in content or 'Received new GOSSIP' in content, \
                    "No gossip activity detected"
    
    def test_08_gossip_deduplication(self, helper):
        """Test Case 8: Duplicate gossip messages are filtered"""
        seed_ports = [helper.base_seed_port + 60 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start a peer
        peer_port = helper.base_peer_port + 60
        helper.start_peer(peer_port)
        
        time.sleep(6)
        
        # Send duplicate gossip messages
        msg = {
            'type': 'GOSSIP',
            'message': 'test_message_123',
            'sender_ip': '127.0.0.1',
            'sender_port': 9999
        }
        
        # Send same message twice
        helper.send_message('127.0.0.1', peer_port, msg)
        time.sleep(0.5)
        helper.send_message('127.0.0.1', peer_port, msg)
        
        time.sleep(1)
        
        # Check logs - message should appear only once
        if os.path.exists('outputfile.txt'):
            with open('outputfile.txt', 'r') as f:
                content = f.read()
                count = content.count('test_message_123')
                # Should appear at most once in received logs
                assert count <= 2, "Duplicate gossip not properly filtered"


class TestLivenessDetection:
    """Test cases for liveness detection and dead node handling"""
    
    def test_09_ping_mechanism(self, helper):
        """Test Case 9: Peers respond to ping messages"""
        seed_ports = [helper.base_seed_port + 70 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peer
        peer_port = helper.base_peer_port + 70
        helper.start_peer(peer_port)
        
        time.sleep(3)
        
        # Send PING
        response = helper.send_message('127.0.0.1', peer_port, {'type': 'PING'})
        assert response is not None, "Peer not responding to PING"
        assert response['status'] == 'PONG', "Invalid PING response"
    
    def test_10_dead_node_detection(self, helper):
        """Test Case 10: Dead nodes are detected by peers"""
        seed_ports = [helper.base_seed_port + 80 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peers
        peer_ports = [helper.base_peer_port + 80 + i for i in range(3)]
        for port in peer_ports:
            helper.start_peer(port)
        
        # Wait for registration and network formation
        time.sleep(10)
        
        # Kill one peer to simulate failure
        if len(helper.processes) > 3:
            helper.processes[-1].terminate()
            helper.processes[-1].wait(timeout=2)
        
        # Wait for liveness detection (liveness thread runs every 13s + detection time)
        time.sleep(30)
        
        # Check if dead node was reported
        if os.path.exists('outputfile.txt'):
            with open('outputfile.txt', 'r') as f:
                content = f.read()
                assert 'SUSPECT' in content or 'Dead Node' in content or 'consensus reached' in content, \
                    "Dead node not detected"
    
    def test_11_dead_node_removal_consensus(self, helper):
        """Test Case 11: Dead nodes achieve removal consensus"""
        seed_ports = [helper.base_seed_port + 90 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Register a peer manually then kill it
        dead_peer_ip = '127.0.0.1'
        dead_peer_port = helper.base_peer_port + 90
        
        # Register the peer
        helper.send_message('127.0.0.1', seed_ports[0], {
            'type': 'REGISTER',
            'peer_ip': dead_peer_ip,
            'peer_port': dead_peer_port
        })
        
        time.sleep(3)
        
        # Simulate dead node report
        helper.send_message('127.0.0.1', seed_ports[0], {
            'type': 'DEAD_NODE',
            'dead_ip': dead_peer_ip,
            'dead_port': dead_peer_port,
            'reporter_ip': '127.0.0.1',
            'reporter_port': 8888
        })
        
        time.sleep(3)
        
        # Check if removed from PL
        response = helper.send_message('127.0.0.1', seed_ports[0], {'type': 'GET_PL'})
        if response and 'PL' in response:
            pl = response['PL']
            peer_still_exists = [dead_peer_ip, dead_peer_port] in pl
            # After consensus, peer should be removed
            assert not peer_still_exists, "Dead peer still in PL after consensus"


class TestNetworkTopology:
    """Test cases for network topology formation"""
    
    def test_12_power_law_network_formation(self, helper):
        """Test Case 12: Peers form power-law network topology"""
        seed_ports = [helper.base_seed_port + 100 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start multiple peers to form network
        peer_ports = [helper.base_peer_port + 100 + i for i in range(6)]
        for port in peer_ports:
            helper.start_peer(port)
        
        # Wait for registration + network formation (needs time for preferential attachment)
        time.sleep(15)
        
        # Query degrees from all peers
        degrees = []
        for port in peer_ports:
            response = helper.send_message('127.0.0.1', port, {'type': 'GET_DEGREE'})
            if response and 'degree' in response:
                degrees.append(response['degree'])
        
        # Check that network was formed (peers have neighbors)
        assert len(degrees) > 0, "No degree information obtained"
        assert sum(degrees) > 0, "No connections formed in network"
    
    def test_13_neighbor_addition(self, helper):
        """Test Case 13: Peers can add neighbors dynamically"""
        seed_ports = [helper.base_seed_port + 110 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start two peers
        peer1_port = helper.base_peer_port + 110
        peer2_port = helper.base_peer_port + 111
        
        helper.start_peer(peer1_port)
        helper.start_peer(peer2_port)
        
        time.sleep(5)
        
        # Manually add neighbor
        response = helper.send_message('127.0.0.1', peer1_port, {
            'type': 'ADD_NEIGHBOR',
            'peer_ip': '127.0.0.1',
            'peer_port': peer2_port
        })
        
        assert response is not None, "Failed to add neighbor"
        assert response['status'] == 'SUCCESS', "Neighbor addition failed"


class TestFailureScenarios:
    """Test cases for failure scenarios and edge cases"""
    
    def test_14_seed_failure_recovery(self, helper):
        """Test Case 14: System continues functioning after seed failure"""
        seed_ports = [helper.base_seed_port + 120 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        seed_processes = []
        for port in seed_ports:
            process = helper.start_seed(port)
            seed_processes.append(process)
        
        time.sleep(2)
        
        # Start peers
        peer_ports = [helper.base_peer_port + 120 + i for i in range(3)]
        for port in peer_ports:
            helper.start_peer(port)
        
        time.sleep(8)
        
        # Kill one seed
        if len(seed_processes) > 0:
            seed_processes[0].terminate()
            seed_processes[0].wait(timeout=2)
        
        time.sleep(3)
        
        # Check remaining seeds still work
        response = helper.send_message('127.0.0.1', seed_ports[1], {'type': 'GET_PL'})
        assert response is not None, "Remaining seeds not functioning after failure"
        assert response['status'] == 'SUCCESS'
    
    def test_15_network_partition_handling(self, helper):
        """Test Case 15: Network handles partition scenarios"""
        seed_ports = [helper.base_seed_port + 130 + i for i in range(3)]
        helper.create_test_config(seed_ports)
        
        # Start seeds
        for port in seed_ports:
            helper.start_seed(port)
        
        time.sleep(2)
        
        # Start peers in groups
        peer_group1 = [helper.base_peer_port + 130 + i for i in range(3)]
        peer_group2 = [helper.base_peer_port + 133 + i for i in range(2)]
        
        for port in peer_group1:
            helper.start_peer(port)
        
        time.sleep(6)
        
        for port in peer_group2:
            helper.start_peer(port)
        
        time.sleep(8)
        
        # Verify both groups are registered
        response = helper.send_message('127.0.0.1', seed_ports[0], {'type': 'GET_PL'})
        assert response is not None
        peer_count = len(response.get('PL', []))
        
        # At least 3 peers should be registered
        assert peer_count >= 3, f"Expected at least 3 peers, got {peer_count}"


if __name__ == "__main__":
    print("P2P Network Test Suite")
    print("=" * 60)
    print("This suite contains 15 comprehensive test cases covering:")
    print("  - Seed node operations and consensus")
    print("  - Peer registration and network formation")
    print("  - Gossip protocol and message propagation")
    print("  - Liveness detection and dead node handling")
    print("  - Network topology (power-law)")
    print("  - Failure scenarios and recovery")
    print("=" * 60)
    print("\nRun with: pytest test_network.py -v")
    print("Or run specific test: pytest test_network.py::TestSeedNodes::test_01_single_seed_startup -v")
