#!/usr/bin/env python3
"""
DICOM Network Probe
Scans and tests DICOM nodes to discover their AE Titles and capabilities
"""

import sys
import socket
import logging
from datetime import datetime
from pynetdicom import AE, evt, VerificationPresentationContexts
from pynetdicom.sop_class import (
    Verification,
    PatientRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelFind,
    CTImageStorage,
    MRImageStorage
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DICOMProbe')

# Common AE Titles to try
COMMON_AE_TITLES = [
    'RA600',
    'LQC6',
    'GEPACS',
    'PACS',
    'DCM4CHEE',
    'ORTHANC',
    'CONQUEST',
    'STORESCP',
    'ANY-SCP',
    'CGHLEA3',
    'CGHHEA2'
]

# Common ports to scan
COMMON_PORTS = [104, 4100, 11112, 11120, 4242]

def test_echo(host, port, calling_ae, called_ae, timeout=3):
    """Test C-ECHO to a DICOM node"""
    try:
        ae = AE(ae_title=calling_ae)
        ae.add_requested_context(Verification)

        assoc = ae.associate(host, port, ae_title=called_ae, max_pdu=0)

        if assoc.is_established:
            # Send C-ECHO
            status = assoc.send_c_echo()
            assoc.release()

            if status and status.Status == 0x0000:
                return True, "C-ECHO successful"
            else:
                return False, f"C-ECHO failed with status: {status.Status if status else 'No status'}"
        else:
            return False, "Association rejected"

    except socket.timeout:
        return False, "Connection timeout"
    except socket.error as e:
        return False, f"Socket error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def scan_local_network(base_ip=None):
    """Scan local network for DICOM nodes"""
    results = []

    # Get local IP if not provided
    if not base_ip:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            base_ip = '.'.join(local_ip.split('.')[:-1])
            logger.info(f"Scanning network: {base_ip}.x")
        except:
            base_ip = "192.168.1"
            logger.warning(f"Could not detect local network, using default: {base_ip}.x")

    # Common IP ranges for DICOM servers
    ip_ranges = [
        f"{base_ip}.{i}" for i in range(1, 255)
    ]

    # Add specific IPs from config if available
    known_ips = [
        "10.30.191.120",  # LK PACS
        "10.30.190.52",   # LK LTA
        "10.31.191.120",  # TY PACS
        "10.31.191.52",   # TY LTA
        "127.0.0.1"       # Localhost
    ]

    for ip in known_ips:
        if ip not in ip_ranges:
            ip_ranges.append(ip)

    logger.info(f"Testing {len(ip_ranges)} IP addresses with {len(COMMON_PORTS)} ports each...")

    for ip in ip_ranges:
        for port in COMMON_PORTS:
            # Quick port scan first
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((ip, port))
            sock.close()

            if result == 0:
                logger.info(f"Found open port: {ip}:{port}")

                # Try different AE Title combinations
                for called_ae in COMMON_AE_TITLES:
                    for calling_ae in ['GEPACS', 'LQC6', 'SCU']:
                        success, message = test_echo(ip, port, calling_ae, called_ae, timeout=2)

                        if success:
                            result = {
                                'ip': ip,
                                'port': port,
                                'calling_ae': calling_ae,
                                'called_ae': called_ae,
                                'status': 'SUCCESS',
                                'message': message
                            }
                            results.append(result)
                            logger.info(f"✓ Found DICOM node: {ip}:{port} (Called AE: {called_ae}, Calling AE: {calling_ae})")
                            break  # Found working combination

                    if results and results[-1]['ip'] == ip and results[-1]['port'] == port:
                        break  # Already found for this IP:port

    return results

def test_specific_node(ip, port, ae_title=None):
    """Test a specific DICOM node with various AE Titles"""
    logger.info(f"\nTesting DICOM node at {ip}:{port}")
    logger.info("=" * 50)

    results = []

    if ae_title:
        # Test specific AE Title
        ae_titles_to_test = [ae_title]
    else:
        # Test all common AE Titles
        ae_titles_to_test = COMMON_AE_TITLES

    for called_ae in ae_titles_to_test:
        for calling_ae in ['GEPACS', 'LQC6', 'SCU', 'ANY-SCU']:
            logger.info(f"Testing: Calling AE='{calling_ae}' -> Called AE='{called_ae}'")

            success, message = test_echo(ip, port, calling_ae, called_ae)

            result = {
                'calling_ae': calling_ae,
                'called_ae': called_ae,
                'success': success,
                'message': message
            }
            results.append(result)

            if success:
                logger.info(f"  ✓ SUCCESS: {message}")
                logger.info(f"  → Working configuration found!")
                logger.info(f"  → Calling AE: '{calling_ae}'")
                logger.info(f"  → Called AE: '{called_ae}'")
            else:
                logger.debug(f"  ✗ FAILED: {message}")

    # Summary
    successful = [r for r in results if r['success']]
    if successful:
        logger.info(f"\n✓ Found {len(successful)} working configuration(s):")
        for r in successful:
            logger.info(f"  - Calling AE: '{r['calling_ae']}' -> Called AE: '{r['called_ae']}'")
    else:
        logger.warning(f"\n✗ No working configurations found for {ip}:{port}")

    return results

def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(description='DICOM Network Probe')
    parser.add_argument('--scan', action='store_true', help='Scan local network for DICOM nodes')
    parser.add_argument('--ip', help='Test specific IP address')
    parser.add_argument('--port', type=int, help='Test specific port')
    parser.add_argument('--ae-title', help='Test specific AE Title')
    parser.add_argument('--calling-ae', help='Use specific calling AE Title')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "="*60)
    print("DICOM Network Probe")
    print("="*60)

    if args.scan:
        print("\nScanning local network for DICOM nodes...")
        print("This may take a few minutes...\n")

        results = scan_local_network()

        if results:
            print(f"\n✓ Found {len(results)} DICOM node(s):\n")
            for r in results:
                print(f"  {r['ip']}:{r['port']}")
                print(f"    Calling AE: {r['calling_ae']}")
                print(f"    Called AE: {r['called_ae']}")
                print(f"    Status: {r['message']}")
                print()
        else:
            print("\n✗ No DICOM nodes found")

    elif args.ip and args.port:
        results = test_specific_node(args.ip, args.port, args.ae_title)

    elif args.ip or args.port:
        print("Error: Both --ip and --port are required for testing specific node")
        sys.exit(1)

    else:
        # Test localhost by default
        print("\nTesting common local DICOM ports...")
        found_any = False

        for port in COMMON_PORTS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()

            if result == 0:
                print(f"\nFound open port: localhost:{port}")
                test_specific_node('127.0.0.1', port)
                found_any = True

        if not found_any:
            print("\nNo DICOM services found on localhost")
            print("\nTry:")
            print("  python dicom_probe.py --scan                    # Scan network")
            print("  python dicom_probe.py --ip 10.0.0.1 --port 104  # Test specific node")

if __name__ == '__main__':
    main()