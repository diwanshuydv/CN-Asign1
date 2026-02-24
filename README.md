# P2P Gossip Network Programming Assignment

This project implements a gossip-based P2P network using Python. It consists of multiple Seed nodes and Peer nodes that maintain connectivity, distribute messages using a Gossip Protocol, and manage membership changes via a consensus mechanism.

## Files Provided
- `seed.py`: The seed node implementation. Handles peer registration and removal using a consensus protocol among the seeds.
- `peer.py`: The peer node implementation. Connects to the network, achieves a power-law connectivity topology, distributes gossip messages, and actively monitors neighbor liveness.
- `config.csv`: Configuration file holding the IP:Port of the seeds.
- `README.md`: Execution instructions and design description.

## Requirements
- Python 3.7+ installed.
- Access to terminal (Linux/macOS) or Command Prompt (Windows).
- Ensure required ports are unblocked.

## Execution Instructions

1. **Configure the network:**
   Edit the `config.csv` file to define seed nodes. Each line must be in the `IP,Port` format.
   Example `config.csv`:
   ```csv
   127.0.0.1,5001
   127.0.0.1,5002
   127.0.0.1,5003
   ```

2. **Start the Seed Nodes:**
   Start $n$ seed nodes (matching the count in `config.csv`). Open separate terminal windows for each:
   ```bash
   python3 seed.py config.csv 5001
   python3 seed.py config.csv 5002
   python3 seed.py config.csv 5003
   ```
   *Logs will be written to `outputfile_seed_<port>.txt`.*

3. **Start the Peer Nodes:**
   In new terminals, start multiple peers using different available ports.
   ```bash
   python3 peer.py config.csv 6001
   python3 peer.py config.csv 6002
   python3 peer.py config.csv 6003
   ...
   ```
   *Logs will be written to `outputfile_peer_<port>.txt`.*

   You can optionally specify the exact IP address the peer should use:
   ```bash
   python3 peer.py config.csv 6001 127.0.0.1
   ```

## Design Overview
1. **Consensus**: Consensus is run across seed nodes to validate Peer Registration (i.e. `PROPOSE_ADD`, `VOTE_ADD`, `COMMIT_ADD`) and Peer Removal upon failure (`PROPOSE_REMOVE`). A majority of seeds (`floor(n/2) + 1`) is required to confirm the changes.
2. **Power Law Topology Formation**: Peers query neighbors from the union-PL list obtained from the seed nodes. By gathering the current active degree of peers, new peers establish connections probabilistically using Preferential Attachment, selecting a maximum of `c=3` edges prioritizing highly-connected nodes.
3. **Gossip Distribution**: Nodes limit message traversals to prevent network congestion by caching message hashes (`ML` list).
4. **Liveness Detection**: Handled by background threading monitoring socket states and ping latency. Suspected faults trigger localized Peer-Level agreement (broadcasting suspects locally to neighbor peers) before reporting `DEAD_NODE` universally to `Seeds`.
