import socket
import sys
import json
import threading
import time
import os
import platform
import subprocess
import hashlib
import random
from collections import defaultdict

class PeerNode:
    def __init__(self, config_file, my_port, my_ip='127.0.0.1'):
        self.config_file = config_file
        self.my_port = int(my_port)
        self.my_ip = my_ip
        self.seeds = []
        self.load_config()
        
        self.neighbors = set()
        self.ML = set() # Message List for gossip
        self.lock = threading.Lock()
        
        # CORRECTED: Single output file as per assignment requirements
        self.log_file = open("outputfile.txt", "a")
        
        # Suspects: key=(dead_ip, dead_port), value=set(reporters)
        self.suspects = defaultdict(set)
        self.dead_nodes = set()
        
        self.msg_count = 0
        self.max_msg = 10

    def load_config(self):
        with open(self.config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(',')
                    self.seeds.append((parts[0], int(parts[1])))

    def log(self, msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        # Include identity in the log since multiple nodes write to the same file
        log_entry = f"[Peer {self.my_port}] [{timestamp}] {msg}"
        print(log_entry)
        try:
            self.log_file.write(log_entry + "\n")
            self.log_file.flush()
        except ValueError:
            pass

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', self.my_port))
        server.listen(10)
        self.log(f"Peer started on {self.my_ip}:{self.my_port}")
        
        # Start server listener
        threading.Thread(target=self.accept_connections, args=(server,), daemon=True).start()
        
        # Registration and topology building
        union_pl = self.register_with_seeds()
        self.form_power_law_network(union_pl)
        
        # Start background threads
        threading.Thread(target=self.gossip_thread_loop, daemon=True).start()
        threading.Thread(target=self.liveness_thread_loop, daemon=True).start()
        
        # Keep main thread alive
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
        self.log_file.close()

    def accept_connections(self, server):
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                pass

    def handle_client(self, conn, addr):
        try:
            data = conn.recv(8192).decode('utf-8')
            if not data: return
            msg = json.loads(data)
            self.process_message(msg, conn)
        except Exception:
            pass
        finally:
            conn.close()

    def send_to_node(self, ip, port, msg):
        try:
            with socket.create_connection((ip, port), timeout=2) as s:
                s.sendall(json.dumps(msg).encode('utf-8'))
                return True
        except Exception:
            return False

    def send_and_recv(self, ip, port, msg):
        try:
            with socket.create_connection((ip, port), timeout=2) as s:
                s.sendall(json.dumps(msg).encode('utf-8'))
                data = s.recv(8192).decode('utf-8')
                if data:
                    return json.loads(data)
        except Exception:
            pass
        return None

    def broadcast_to_neighbors(self, msg, exclude_ip=None, exclude_port=None):
        with self.lock:
            nbs = list(self.neighbors)
        for nip, nport in nbs:
            if nip == exclude_ip and nport == exclude_port:
                continue
            threading.Thread(target=self.send_to_node, args=(nip, nport, msg), daemon=True).start()

    def register_with_seeds(self):
        n = len(self.seeds)
        k = n // 2 + 1
        curr_seeds = self.seeds.copy()
        random.shuffle(curr_seeds)
        chosen_seeds = curr_seeds[:k]
        
        self.log(f"Registering with seeds: {chosen_seeds}")
        for sip, sport in chosen_seeds:
            self.send_to_node(sip, sport, {
                'type': 'REGISTER',
                'peer_ip': self.my_ip,
                'peer_port': self.my_port
            })
            
        time.sleep(3) # Wait for seeds to reach consensus
        
        union_pl = set()
        for sip, sport in chosen_seeds:
            res = self.send_and_recv(sip, sport, {'type': 'GET_PL'})
            if res and res.get('status') == 'SUCCESS':
                pl = res.get('PL', [])
                for p in pl:
                    if p[0] != self.my_ip or p[1] != self.my_port:
                        union_pl.add(tuple(p))
                        
        self.log(f"Union PL from seeds: {union_pl}")
        return union_pl

    def form_power_law_network(self, union_pl):
        degrees = {}
        for pip, pport in union_pl:
            res = self.send_and_recv(pip, pport, {'type': 'GET_DEGREE'})
            if res and res.get('status') == 'SUCCESS':
                degrees[(pip, pport)] = res.get('degree', 0)
                
        self.log(f"Degrees of active peers: {degrees}")
        max_c = 3
        # Use min to avoid errors if fewer peers exist
        needed = random.randint(1, max_c)
        c = min(needed, len(degrees))
        
        if c == 0:
            return
            
        # Preferential Attachment Logic
        selected = []
        pool = list(degrees.keys())
        
        while len(selected) < c and pool:
            D = [degrees[p] for p in pool]
            total_m = sum(D)
            
            if total_m == 0:
                probs = [1.0/len(pool)] * len(pool)
            else:
                probs = [d/total_m for d in D]
            
            r = random.random()
            cum = 0
            idx = len(pool) - 1
            for i, p in enumerate(probs):
                cum += p
                if r <= cum:
                    idx = i
                    break
            selected.append(pool.pop(idx))
                
        self.log(f"Selected neighbors based on power law: {selected}")
        with self.lock:
            for pip, pport in selected:
                self.neighbors.add((pip, pport))
                
        for pip, pport in selected:
            self.send_to_node(pip, pport, {
                'type': 'ADD_NEIGHBOR',
                'peer_ip': self.my_ip,
                'peer_port': self.my_port
            })

    def process_message(self, msg, conn):
        mtype = msg.get('type')
        
        if mtype == 'GET_DEGREE':
            with self.lock:
                deg = len(self.neighbors)
            conn.sendall(json.dumps({'status': 'SUCCESS', 'degree': deg}).encode('utf-8'))
            
        elif mtype == 'ADD_NEIGHBOR':
            pip = msg['peer_ip']
            pport = msg['peer_port']
            with self.lock:
                self.neighbors.add((pip, pport))
            self.log(f"Added neighbor {pip}:{pport}")
            conn.sendall(json.dumps({'status': 'SUCCESS'}).encode('utf-8'))
            
        elif mtype == 'PING':
            conn.sendall(json.dumps({'status': 'PONG'}).encode('utf-8'))
            
        elif mtype == 'GOSSIP':
            message_str = msg['message']
            sender_ip = msg['sender_ip']
            sender_port = msg['sender_port']
            msg_hash = hashlib.sha256(message_str.encode()).hexdigest()
            
            with self.lock:
                if msg_hash in self.ML:
                    return
                # Cap ML size to prevent memory leak
                if len(self.ML) > 5000:
                    self.ML.pop()
                self.ML.add(msg_hash)
                
            self.log(f"Received new GOSSIP from {sender_ip}:{sender_port} -> {message_str}")
            
            # Forward gossip
            gossip_data = {
                'type': 'GOSSIP',
                'message': message_str,
                'sender_ip': self.my_ip,
                'sender_port': self.my_port
            }
            self.broadcast_to_neighbors(gossip_data, exclude_ip=sender_ip, exclude_port=sender_port)
            
        elif mtype == 'SUSPECT':
            suspect_ip = msg['suspect_ip']
            suspect_port = msg['suspect_port']
            reporter_ip = msg['reporter_ip']
            reporter_port = msg['reporter_port']
            ttl = msg.get('ttl', 0)
            
            self.log(f"Received SUSPECT for {suspect_ip}:{suspect_port} from {reporter_ip}:{reporter_port} (TTL:{ttl})")
            
            self.handle_suspicion(suspect_ip, suspect_port, reporter_ip, reporter_port)
            
            # Forward if TTL > 0 to allow consensus among disjoint neighbors
            if ttl > 0:
                msg['ttl'] = ttl - 1
                self.broadcast_to_neighbors(msg, exclude_ip=sender_ip if 'sender_ip' in msg else None)

    def gossip_thread_loop(self):
        time.sleep(5)
        while self.msg_count < self.max_msg:
            time.sleep(5)
            self.msg_count += 1
            ts_str = str(time.time())
            msg_str = f"{ts_str}:{self.my_ip}:{self.msg_count}"
            msg_hash = hashlib.sha256(msg_str.encode()).hexdigest()
            
            with self.lock:
                self.ML.add(msg_hash)
            
            self.log(f"Generating GOSSIP: {msg_str}")
            gossip_data = {
                'type': 'GOSSIP',
                'message': msg_str,
                'sender_ip': self.my_ip,
                'sender_port': self.my_port
            }
            self.broadcast_to_neighbors(gossip_data)

    def ping_and_check(self, ip, port):
        # 1. System level ping
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        res = subprocess.call(['ping', param, '1', '-W', '1', ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res != 0:
            return False
            
        # 2. Socket check
        try:
            with socket.create_connection((ip, port), timeout=2) as s:
                s.sendall(json.dumps({'type': 'PING'}).encode('utf-8'))
                data = s.recv(1024).decode('utf-8')
                if data and json.loads(data).get('status') == 'PONG':
                    return True
        except Exception:
            return False
        return False

    def liveness_thread_loop(self):
        time.sleep(10)
        while True:
            time.sleep(13)
            with self.lock:
                nbs = list(self.neighbors)
                
            dead_list = []
            for nip, nport in nbs:
                alive = self.ping_and_check(nip, nport)
                if not alive:
                    dead_list.append((nip, nport))
                    
            for nip, nport in dead_list:
                # Log suspicion locally
                self.handle_suspicion(nip, nport, self.my_ip, self.my_port)
                
                # Broadcast suspicion to neighbors with TTL=2 (radius of 2)
                # This ensures disjoint neighbors of the dead node hear about it
                suspect_msg = {
                    'type': 'SUSPECT',
                    'suspect_ip': nip,
                    'suspect_port': nport,
                    'reporter_ip': self.my_ip,
                    'reporter_port': self.my_port,
                    'ttl': 2
                }
                self.broadcast_to_neighbors(suspect_msg)

    def handle_suspicion(self, suspect_ip, suspect_port, reporter_ip, reporter_port):
        with self.lock:
            if (suspect_ip, suspect_port) in self.dead_nodes:
                return

            self.suspects[(suspect_ip, suspect_port)].add((reporter_ip, reporter_port))
            
            # Consensus Threshold:
            # If network is very small (e.g. 1 neighbor), 1 vote is consensus.
            # Otherwise require at least 2 independent reports.
            threshold = 2
            
            unique_reporters = len(self.suspects[(suspect_ip, suspect_port)])
            
            if unique_reporters >= threshold:
                self.log(f"Peer-level consensus reached for Dead Node {suspect_ip}:{suspect_port} (Votes: {unique_reporters})")
                self.dead_nodes.add((suspect_ip, suspect_port))
                
                if (suspect_ip, suspect_port) in self.neighbors:
                    self.neighbors.remove((suspect_ip, suspect_port))
                
                # Report to seeds after peer consensus
                threading.Thread(target=self.report_dead_node_to_seeds, args=(suspect_ip, suspect_port), daemon=True).start()

    def report_dead_node_to_seeds(self, dead_ip, dead_port):
        self.log(f"Reporting Dead Node {dead_ip}:{dead_port} to seeds.")
        msg = {
            'type': 'DEAD_NODE',
            'dead_ip': dead_ip,
            'dead_port': dead_port,
            'timestamp': str(time.time()),
            'reporter_ip': self.my_ip,
            'reporter_port': self.my_port
        }
        for sip, sport in self.seeds:
            self.send_to_node(sip, sport, msg)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python peer.py <config.csv> <port> [my_ip]")
        sys.exit(1)
        
    config_file = sys.argv[1]
    port = sys.argv[2]
    ip = sys.argv[3] if len(sys.argv) > 3 else '127.0.0.1'
    
    peer = PeerNode(config_file, port, ip)
    peer.start()