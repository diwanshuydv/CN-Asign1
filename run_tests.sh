#!/bin/bash

# P2P Network Test Suite Runner
# This script helps run the test suite with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_color() {
    color=$1
    message=$2
    echo -e "${color}${message}${NC}"
}

# Print header
print_header() {
    echo ""
    print_color "$BLUE" "=================================================="
    print_color "$BLUE" "  P2P Network Test Suite Runner"
    print_color "$BLUE" "=================================================="
    echo ""
}

# Check prerequisites
check_prerequisites() {
    print_color "$YELLOW" "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_color "$RED" "Error: python3 is not installed"
        exit 1
    fi
    print_color "$GREEN" "✓ Python3 found"
    
    # Check pytest
    if ! python3 -c "import pytest" &> /dev/null; then
        print_color "$RED" "Error: pytest is not installed"
        echo "Install with: pip3 install pytest pytest-timeout"
        exit 1
    fi
    print_color "$GREEN" "✓ pytest found"
    
    # Check required files
    if [ ! -f "seed.py" ]; then
        print_color "$RED" "Error: seed.py not found"
        exit 1
    fi
    print_color "$GREEN" "✓ seed.py found"
    
    if [ ! -f "peer.py" ]; then
        print_color "$RED" "Error: peer.py not found"
        exit 1
    fi
    print_color "$GREEN" "✓ peer.py found"
    
    if [ ! -f "config.csv" ]; then
        print_color "$RED" "Error: config.csv not found"
        exit 1
    fi
    print_color "$GREEN" "✓ config.csv found"
    
    if [ ! -f "test_network.py" ]; then
        print_color "$RED" "Error: test_network.py not found"
        exit 1
    fi
    print_color "$GREEN" "✓ test_network.py found"
    
    echo ""
}

# Cleanup function
cleanup() {
    print_color "$YELLOW" "Cleaning up..."
    pkill -f "python.*seed.py" 2>/dev/null || true
    pkill -f "python.*peer.py" 2>/dev/null || true
    rm -f outputfile.txt test_config.csv 2>/dev/null || true
    print_color "$GREEN" "✓ Cleanup complete"
}

# Show menu
show_menu() {
    echo "Select test mode:"
    echo "  1) Run all tests (15 test cases)"
    echo "  2) Run seed node tests only (3 tests)"
    echo "  3) Run peer node tests only (3 tests)"
    echo "  4) Run gossip protocol tests only (2 tests)"
    echo "  5) Run liveness detection tests only (3 tests)"
    echo "  6) Run network topology tests only (2 tests)"
    echo "  7) Run failure scenario tests only (2 tests)"
    echo "  8) Run specific test by number (1-15)"
    echo "  9) Quick test (first 3 tests only)"
    echo "  10) Cleanup and exit"
    echo ""
}

# Run tests based on selection
run_tests() {
    case $1 in
        1)
            print_color "$GREEN" "Running all 15 test cases..."
            python3 -m pytest test_network.py -v
            ;;
        2)
            print_color "$GREEN" "Running seed node tests..."
            python3 -m pytest test_network.py::TestSeedNodes -v
            ;;
        3)
            print_color "$GREEN" "Running peer node tests..."
            python3 -m pytest test_network.py::TestPeerNodes -v
            ;;
        4)
            print_color "$GREEN" "Running gossip protocol tests..."
            python3 -m pytest test_network.py::TestGossipProtocol -v
            ;;
        5)
            print_color "$GREEN" "Running liveness detection tests..."
            python3 -m pytest test_network.py::TestLivenessDetection -v
            ;;
        6)
            print_color "$GREEN" "Running network topology tests..."
            python3 -m pytest test_network.py::TestNetworkTopology -v
            ;;
        7)
            print_color "$GREEN" "Running failure scenario tests..."
            python3 -m pytest test_network.py::TestFailureScenarios -v
            ;;
        8)
            echo ""
            echo "Enter test number (1-15):"
            read test_num
            case $test_num in
                1) python3 -m pytest test_network.py::TestSeedNodes::test_01_single_seed_startup -v ;;
                2) python3 -m pytest test_network.py::TestSeedNodes::test_02_multiple_seeds_startup -v ;;
                3) python3 -m pytest test_network.py::TestSeedNodes::test_03_peer_registration_consensus -v ;;
                4) python3 -m pytest test_network.py::TestPeerNodes::test_04_peer_startup_and_registration -v ;;
                5) python3 -m pytest test_network.py::TestPeerNodes::test_05_multiple_peers_parallel_registration -v ;;
                6) python3 -m pytest test_network.py::TestPeerNodes::test_06_peer_degree_query -v ;;
                7) python3 -m pytest test_network.py::TestGossipProtocol::test_07_gossip_message_propagation -v ;;
                8) python3 -m pytest test_network.py::TestGossipProtocol::test_08_gossip_deduplication -v ;;
                9) python3 -m pytest test_network.py::TestLivenessDetection::test_09_ping_mechanism -v ;;
                10) python3 -m pytest test_network.py::TestLivenessDetection::test_10_dead_node_detection -v ;;
                11) python3 -m pytest test_network.py::TestLivenessDetection::test_11_dead_node_removal_consensus -v ;;
                12) python3 -m pytest test_network.py::TestNetworkTopology::test_12_power_law_network_formation -v ;;
                13) python3 -m pytest test_network.py::TestNetworkTopology::test_13_neighbor_addition -v ;;
                14) python3 -m pytest test_network.py::TestFailureScenarios::test_14_seed_failure_recovery -v ;;
                15) python3 -m pytest test_network.py::TestFailureScenarios::test_15_network_partition_handling -v ;;
                *)
                    print_color "$RED" "Invalid test number"
                    exit 1
                    ;;
            esac
            ;;
        9)
            print_color "$GREEN" "Running quick test (first 3 tests)..."
            python3 -m pytest test_network.py::TestSeedNodes -v
            ;;
        10)
            cleanup
            print_color "$GREEN" "Goodbye!"
            exit 0
            ;;
        *)
            print_color "$RED" "Invalid selection"
            exit 1
            ;;
    esac
}

# Main execution
main() {
    print_header
    
    # Cleanup any previous runs
    cleanup
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Show menu
    show_menu
    
    # Get user selection
    echo "Enter your choice (1-10):"
    read choice
    echo ""
    
    # Run selected tests
    run_tests $choice
    
    # Final cleanup
    echo ""
    cleanup
    
    echo ""
    print_color "$GREEN" "Test execution completed!"
    echo ""
    print_color "$BLUE" "For detailed documentation, see: TEST_DOCUMENTATION.md"
    echo ""
}

# Handle Ctrl+C
trap cleanup EXIT INT TERM

# Run main function
main
