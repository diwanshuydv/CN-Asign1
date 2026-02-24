import socket
import sys
import json
import threading
import time

class SeedNode:
    def __init__(self, config_file, my_port):
        self.config_file = config_file
        self.my_port = int(my_port)
        self.seeds = []
        # Default IP; will be updated from config
        self.my_ip = '127.0.0.1' 
        self.load_config()
        
        self.PL = set()
        self.lock = threading.Lock()
        
        # CORRECTED: Single output file as per assignment requirements
        self.log_file = open("outputfile.txt", "a")
        
        self.proposals = {}
        self.committed = set()

    def load_config(self):
        found = False
        with open(self.config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(',')
                    ip = parts[0]
                    port = int(parts[1])
                    self.seeds.append((ip, port))
                    
                    if port == self.my_port:
                        self.my_ip = ip
                        found = True
        
        if not found:
            print(f"Warning: Port {self.my_port} not found in config. Using default IP {self.my_ip}")

    def log(self, msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        # Include identity in the log since multiple nodes write to the same file
        log_entry = f"[Seed {self.my_port}] [{timestamp}] {msg}"
        print(log_entry)
        try:
            self.log_file.write(log_entry + "\n")
            self.log_file.flush()
        except ValueError:
            pass # File might be closed

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(('0.0.0.0', self.my_port))
        except OSError as e:
            self.log(f"Failed to bind port {self.my_port}: {e}")
            sys.exit(1)
            
        server.listen(10)
        self.log(f"Seed started on {self.my_ip}:{self.my_port}")
        
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"Error accepting connection: {e}")
        
        self.log_file.close()

    def handle_client(self, conn, addr):
        try:
            data = conn.recv(8192).decode('utf-8')
            if not data: return
            msg = json.loads(data)
            self.process_message(msg, conn)
        except json.JSONDecodeError:
            pass
        except Exception as e:
            self.log(f"Error handling client: {e}")
        finally:
            conn.close()

    def send_to_seed(self, seed_ip, seed_port, msg):
        if seed_ip == self.my_ip and seed_port == self.my_port:
            return
        try:
            with socket.create_connection((seed_ip, seed_port), timeout=2) as s:
                s.sendall(json.dumps(msg).encode('utf-8'))
        except Exception:
            pass

    def broadcast_to_seeds(self, msg):
        for ip, port in self.seeds:
            if ip == self.my_ip and port == self.my_port:
                continue
            threading.Thread(target=self.send_to_seed, args=(ip, port, msg), daemon=True).start()

    def process_message(self, msg, conn):
        mtype = msg.get('type')
        
        if mtype == 'REGISTER':
            peer_ip = msg['peer_ip']
            peer_port = msg['peer_port']
            self.log(f"Received REGISTER from peer {peer_ip}:{peer_port}")
            with self.lock:
                if (peer_ip, peer_port) in self.PL:
                    conn.sendall(json.dumps({'status': 'ALREADY_REGISTERED'}).encode('utf-8'))
                    return
            
            prop_key = f"{peer_ip}:{peer_port}:ADD"
            with self.lock:
                if prop_key not in self.proposals:
                    self.proposals[prop_key] = set()
                self.proposals[prop_key].add((self.my_ip, self.my_port))
            
            self.log(f"Proposing ADD for {peer_ip}:{peer_port}")
            self.broadcast_to_seeds({
                'type': 'PROPOSE_ADD',
                'peer_ip': peer_ip,
                'peer_port': peer_port,
                'sender_ip': self.my_ip,
                'sender_port': self.my_port
            })
            self.check_consensus_add(peer_ip, peer_port, prop_key)
            conn.sendall(json.dumps({'status': 'PROPOSAL_STARTED'}).encode('utf-8'))

        elif mtype == 'PROPOSE_ADD':
            peer_ip = msg['peer_ip']
            peer_port = msg['peer_port']
            sender_ip = msg['sender_ip']
            sender_port = msg['sender_port']
            self.log(f"Received PROPOSE_ADD for {peer_ip}:{peer_port} from {sender_ip}:{sender_port}")
            self.send_to_seed(sender_ip, sender_port, {
                'type': 'VOTE_ADD',
                'peer_ip': peer_ip,
                'peer_port': peer_port,
                'voter_ip': self.my_ip,
                'voter_port': self.my_port
            })

        elif mtype == 'VOTE_ADD':
            peer_ip = msg['peer_ip']
            peer_port = msg['peer_port']
            voter_ip = msg['voter_ip']
            voter_port = msg['voter_port']
            prop_key = f"{peer_ip}:{peer_port}:ADD"
            
            with self.lock:
                if prop_key in self.committed:
                    return
                if prop_key not in self.proposals:
                    self.proposals[prop_key] = set()
                self.proposals[prop_key].add((voter_ip, voter_port))
                
            self.check_consensus_add(peer_ip, peer_port, prop_key)

        elif mtype == 'COMMIT_ADD':
            peer_ip = msg['peer_ip']
            peer_port = msg['peer_port']
            with self.lock:
                self.PL.add((peer_ip, peer_port))
            self.log(f"Received COMMIT_ADD: {peer_ip}:{peer_port} added to PL.")

        elif mtype == 'GET_PL':
            with self.lock:
                pl_list = [list(p) for p in self.PL]
            conn.sendall(json.dumps({'status': 'SUCCESS', 'PL': pl_list}).encode('utf-8'))

        elif mtype == 'DEAD_NODE':
            dead_ip = msg['dead_ip']
            dead_port = msg['dead_port']
            reporter_ip = msg.get('reporter_ip', 'unknown')
            self.log(f"Received DEAD_NODE report for {dead_ip}:{dead_port} from {reporter_ip}")
            
            prop_key = f"{dead_ip}:{dead_port}:REMOVE"
            with self.lock:
                if prop_key not in self.proposals:
                    self.proposals[prop_key] = set()
                self.proposals[prop_key].add((self.my_ip, self.my_port))
                
            self.log(f"Proposing REMOVE for {dead_ip}:{dead_port}")
            self.broadcast_to_seeds({
                'type': 'PROPOSE_REMOVE',
                'dead_ip': dead_ip,
                'dead_port': dead_port,
                'sender_ip': self.my_ip,
                'sender_port': self.my_port
            })
            self.check_consensus_remove(dead_ip, dead_port, prop_key)
            conn.sendall(json.dumps({'status': 'PROPOSAL_STARTED'}).encode('utf-8'))

        elif mtype == 'PROPOSE_REMOVE':
            dead_ip = msg['dead_ip']
            dead_port = msg['dead_port']
            sender_ip = msg['sender_ip']
            sender_port = msg['sender_port']
            self.log(f"Received PROPOSE_REMOVE for {dead_ip}:{dead_port} from {sender_ip}:{sender_port}")
            self.send_to_seed(sender_ip, sender_port, {
                'type': 'VOTE_REMOVE',
                'dead_ip': dead_ip,
                'dead_port': dead_port,
                'voter_ip': self.my_ip,
                'voter_port': self.my_port
            })

        elif mtype == 'VOTE_REMOVE':
            dead_ip = msg['dead_ip']
            dead_port = msg['dead_port']
            voter_ip = msg['voter_ip']
            voter_port = msg['voter_port']
            prop_key = f"{dead_ip}:{dead_port}:REMOVE"
            
            with self.lock:
                if prop_key in self.committed:
                    return
                if prop_key not in self.proposals:
                    self.proposals[prop_key] = set()
                self.proposals[prop_key].add((voter_ip, voter_port))
                
            self.check_consensus_remove(dead_ip, dead_port, prop_key)

        elif mtype == 'COMMIT_REMOVE':
            dead_ip = msg['dead_ip']
            dead_port = msg['dead_port']
            with self.lock:
                if (dead_ip, dead_port) in self.PL:
                    self.PL.remove((dead_ip, dead_port))
            self.log(f"Received COMMIT_REMOVE: {dead_ip}:{dead_port} removed from PL.")

    def check_consensus_add(self, peer_ip, peer_port, prop_key):
        with self.lock:
            if prop_key in self.committed:
                return
            n = len(self.seeds)
            majority = n // 2 + 1
            if len(self.proposals.get(prop_key, set())) >= majority:
                self.PL.add((peer_ip, peer_port))
                self.committed.add(prop_key)
                self.log(f"Consensus reached (ADD): {peer_ip}:{peer_port} added to PL.")
                self.broadcast_to_seeds({
                    'type': 'COMMIT_ADD',
                    'peer_ip': peer_ip,
                    'peer_port': peer_port
                })

    def check_consensus_remove(self, dead_ip, dead_port, prop_key):
        with self.lock:
            if prop_key in self.committed:
                return
            n = len(self.seeds)
            majority = n // 2 + 1
            if len(self.proposals.get(prop_key, set())) >= majority:
                if (dead_ip, dead_port) in self.PL:
                    self.PL.remove((dead_ip, dead_port))
                self.committed.add(prop_key)
                self.log(f"Consensus reached (REMOVE): {dead_ip}:{dead_port} removed from PL.")
                self.broadcast_to_seeds({
                    'type': 'COMMIT_REMOVE',
                    'dead_ip': dead_ip,
                    'dead_port': dead_port
                })

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python seed.py <config.csv> <port>")
        sys.exit(1)
    
    config_file = sys.argv[1]
    port = sys.argv[2]
    
    seed = SeedNode(config_file, port)
    seed.start()