#!/usr/bin/env python3
"""
DICOM Download Tool
Downloads DICOM studies from PACS servers using C-FIND and C-MOVE operations
"""

import os
import sys
import yaml
import logging
import argparse
import csv
import threading
import time
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from pydicom.dataset import Dataset
from pynetdicom import AE, evt, StoragePresentationContexts
from pynetdicom.sop_class import (
    PatientRootQueryRetrieveInformationModelFind,
    PatientRootQueryRetrieveInformationModelMove,
    StudyRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelMove
)


class DICOMDownloader:
    def __init__(self, config_file='config.yaml'):
        """Initialize the DICOM Downloader with configuration"""
        self.config = self.load_config(config_file)
        self.setup_logging()
        self.failed_downloads = []
        self.successful_downloads = []
        self.move_requests = []  # Track all C-MOVE requests

    def load_config(self, config_file):
        """Load configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # Load additional servers from external file if exists
            additional_servers_file = Path('additional_servers.json')
            if additional_servers_file.exists():
                try:
                    with open(additional_servers_file, 'r') as f:
                        additional_servers = json.load(f)
                        config['servers'].update(additional_servers)
                except Exception as e:
                    print(f"Warning: Could not load additional servers: {e}")

            return config
        except Exception as e:
            print(f"Error loading config file: {e}")
            sys.exit(1)

    def setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config['settings'].get('log_level', 'INFO'))
        log_format = '%(asctime)s - %(levelname)s - %(message)s'

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))

        # File handler
        log_dir = Path('logs')
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create log directory '{log_dir}': {e}")
            log_dir = Path('.')

        log_file = log_dir / f"dicom_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format))

        # Configure logger
        self.logger = logging.getLogger('DICOMDownloader')
        self.logger.setLevel(log_level)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)

    def send_c_move(self, server_config, study_uid):
        """Send C-MOVE command to PACS server"""
        # Get destination AE title from config
        destination_ae = self.config.get('move_destination', {}).get('ae_title', 'LQC6')
        calling_ae = self.config.get('local_ae', {}).get('ae_title', 'GEPACS')

        self.logger.info(f"Using Calling AE: {calling_ae}, Destination AE: {destination_ae}")

        # Use configured calling AE title
        ae = AE(ae_title=calling_ae)

        # Add C-MOVE contexts
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelMove)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)

        try:
            # Connect to PACS server
            assoc = ae.associate(
                server_config['ip'],
                server_config['port'],
                ae_title=server_config['ae_title']
            )

            if assoc.is_established:
                self.logger.info(f"Connected to {server_config['description']} for C-MOVE")

                # Create move request dataset
                ds = Dataset()
                ds.QueryRetrieveLevel = 'STUDY'
                ds.StudyInstanceUID = study_uid

                # Send C-MOVE request with destination AE
                responses = assoc.send_c_move(
                    ds,
                    destination_ae,  # Destination AE title from config
                    StudyRootQueryRetrieveInformationModelMove
                )

                move_successful = False
                for (status, identifier) in responses:
                    if status:
                        if status.Status == 0x0000:
                            self.logger.info("C-MOVE completed successfully")
                            move_successful = True
                        elif status.Status == 0xFF00:
                            self.logger.debug("C-MOVE pending...")
                        else:
                            self.logger.warning(f"C-MOVE status: 0x{status.Status:04x}")

                assoc.release()
                return move_successful
            else:
                self.logger.error("Failed to establish association for C-MOVE")
                return False

        except Exception as e:
            self.logger.error(f"Error during C-MOVE: {e}")
            return False

    def query_studies(self, server_config, patient_id, study_date, modality):
        """Perform C-FIND query to find matching studies"""
        # Use configured calling AE title
        calling_ae = self.config.get('local_ae', {}).get('ae_title', 'GEPACS')
        ae = AE(ae_title=calling_ae)
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)

        # Create query dataset
        ds = Dataset()
        ds.QueryRetrieveLevel = 'STUDY'
        ds.PatientID = patient_id
        ds.StudyDate = study_date.replace('-', '')  # Convert YYYY-MM-DD to YYYYMMDD
        if modality:
            ds.Modality = modality  # Use modality as-is (no wildcard needed for exact match)
        ds.StudyInstanceUID = ''  # Request this field to be returned
        ds.PatientName = ''
        ds.StudyDescription = ''

        matching_studies = []

        try:
            timeout = self.config['settings']['query_timeout']
            assoc = ae.associate(
                server_config['ip'],
                server_config['port'],
                ae_title=server_config['ae_title'],
                max_pdu=0
            )

            if assoc.is_established:
                self.logger.info(f"Connected to {server_config['description']} for C-FIND")

                # Send C-FIND request
                responses = assoc.send_c_find(
                    ds,
                    PatientRootQueryRetrieveInformationModelFind
                )

                for (status, identifier) in responses:
                    if status and identifier and status.Status != 0x0000:
                        if hasattr(identifier, 'StudyInstanceUID'):
                            matching_studies.append({
                                'StudyInstanceUID': str(identifier.StudyInstanceUID),
                                'PatientName': str(getattr(identifier, 'PatientName', '')),
                                'StudyDescription': str(getattr(identifier, 'StudyDescription', ''))
                            })

                assoc.release()
                self.logger.info(f"Found {len(matching_studies)} matching studies")

            else:
                self.logger.error(f"Failed to establish association with {server_config['description']}")

        except Exception as e:
            self.logger.error(f"Error during C-FIND: {e}")

        return matching_studies


    def _resolve_server_name(self, server_name: Optional[str]) -> Optional[str]:
        """Resolve server name with case-insensitive matching."""
        if not server_name:
            return None
        server_name = server_name.strip()
        if not server_name:
            return None
        if server_name in self.config['servers']:
            return server_name
        for configured_name in self.config['servers']:
            if configured_name.lower() == server_name.lower():
                return configured_name
        return server_name

    def _expand_server_chain(self, server_name: Optional[str]) -> List[str]:
        """Expand server name to include numeric fallbacks (e.g., LK -> LK1, LK2)."""
        resolved = self._resolve_server_name(server_name)
        if not resolved:
            return []

        candidates = [resolved]
        base_lower = resolved.lower()
        suffixes = []

        for configured_name in self.config['servers']:
            if configured_name.lower().startswith(base_lower) and configured_name.lower() != base_lower:
                remainder = configured_name[len(resolved):]
                if remainder.isdigit():
                    suffixes.append((int(remainder), configured_name))

        for _, name in sorted(suffixes):
            candidates.append(name)

        return candidates

    def _dedupe_servers(self, servers: List[str]) -> List[str]:
        seen = set()
        deduped = []
        for server in servers:
            if server and server not in seen:
                deduped.append(server)
                seen.add(server)
        return deduped

    def build_modality_candidates(
        self,
        primary_modality: Optional[str],
        alt_modalities: Optional[List[str]] = None
    ) -> List[Optional[str]]:
        candidates: List[Optional[str]] = []

        def add_modality(value: Optional[str]) -> None:
            if value is None:
                return
            value = str(value).strip()
            if not value:
                return
            key = value.lower()
            if key not in seen:
                candidates.append(value)
                seen.add(key)

        seen = set()
        add_modality(primary_modality)
        if alt_modalities:
            for alt in alt_modalities:
                add_modality(alt)

        return candidates or [primary_modality]

    def build_server_candidates(
        self,
        primary_server: Optional[str],
        lookup_servers: Optional[List[str]] = None
    ) -> List[str]:
        candidates = []
        if primary_server:
            candidates.extend(self._expand_server_chain(primary_server))

        if lookup_servers:
            lookup_servers = [value for value in lookup_servers if value]
            lookup_all = any(value.lower() == 'all' for value in lookup_servers)
            bases = list(self.config['servers'].keys()) if lookup_all else lookup_servers

            for base in bases:
                candidates.extend(self._expand_server_chain(base))

        return self._dedupe_servers(candidates)

    def process_query_with_lookup(
        self,
        patient_id,
        study_date,
        modality,
        server_name: Optional[str],
        lookup_servers: Optional[List[str]] = None,
        alt_modalities: Optional[List[str]] = None
    ):
        candidates = self.build_server_candidates(server_name, lookup_servers)
        modality_candidates = self.build_modality_candidates(modality, alt_modalities)
        if not candidates:
            reason = "No servers available for lookup"
            self.logger.error(reason)
            self.failed_downloads.append({
                'patient_id': patient_id,
                'date': study_date,
                'modality': modality,
                'server': server_name or 'lookup',
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            })
            return False

        if lookup_servers or len(candidates) > 1:
            self.logger.info(f"Lookup order (servers): {', '.join(candidates)}")
        if alt_modalities:
            self.logger.info(f"Lookup order (modalities): {', '.join(modality_candidates)}")

        last_reason = None
        total_attempts = len(candidates) * len(modality_candidates)
        attempt = 0
        for server_index, candidate in enumerate(candidates, 1):
            for modality_index, modality_value in enumerate(modality_candidates, 1):
                attempt += 1
                modality_label = modality_value or "ANY"
                self.logger.info(
                    f"Lookup attempt {attempt}/{total_attempts}: "
                    f"{candidate} (modality {modality_label})"
                )
                success, reason = self.process_query(
                    patient_id,
                    study_date,
                    modality_value,
                    candidate,
                    record_failure=False
                )
                if success:
                    return True
                last_reason = reason

        failure_reason = last_reason or "All lookup attempts failed"
        modality_list = ', '.join(str(value) for value in modality_candidates if value)
        modality_suffix = f"; modalities [{modality_list}]" if modality_list else ""
        self.failed_downloads.append({
            'patient_id': patient_id,
            'date': study_date,
            'modality': modality,
            'server': server_name or 'lookup',
            'reason': f"{failure_reason}; tried {', '.join(candidates)}{modality_suffix}",
            'timestamp': datetime.now().isoformat()
        })
        return False

    def process_query(self, patient_id, study_date, modality, server_name, record_failure=True):
        """Process a single query"""
        if not server_name:
            reason = "Server not specified"
            self.logger.error(reason)
            if record_failure:
                self.failed_downloads.append({
                    'patient_id': patient_id,
                    'date': study_date,
                    'modality': modality,
                    'server': server_name or 'unknown',
                    'reason': reason,
                    'timestamp': datetime.now().isoformat()
                })
            return False, reason

        resolved_name = self._resolve_server_name(server_name)
        if resolved_name not in self.config['servers']:
            reason = 'Server not configured'
            self.logger.error(f"Server '{server_name}' not found in configuration")
            if record_failure:
                self.failed_downloads.append({
                    'patient_id': patient_id,
                    'date': study_date,
                    'modality': modality,
                    'server': server_name,
                    'reason': reason,
                    'timestamp': datetime.now().isoformat()
                })
            return False, reason

        server_name = resolved_name
        server_config = self.config['servers'][server_name]

        self.logger.info(f"Processing: Patient={patient_id}, Date={study_date}, Modality={modality}, Server={server_name}")

        # Query for studies
        studies = self.query_studies(server_config, patient_id, study_date, modality)

        if not studies:
            reason = 'No matching studies found'
            self.logger.warning(reason)
            if record_failure:
                self.failed_downloads.append({
                    'patient_id': patient_id,
                    'date': study_date,
                    'modality': modality,
                    'server': server_name,
                    'reason': reason,
                    'timestamp': datetime.now().isoformat()
                })
            return False, reason

        # Send C-MOVE for each study
        all_successful = True
        studies_moved = []
        failed_studies = []

        for study in studies:
            study_uid = study['StudyInstanceUID']
            self.logger.info(f"Sending C-MOVE for study: {study_uid}")

            # Send C-MOVE command
            if self.send_c_move(server_config, study_uid):
                studies_moved.append(study_uid)
                self.move_requests.append({
                    'patient_id': patient_id,
                    'date': study_date,
                    'modality': modality,
                    'server': server_name,
                    'study_uid': study_uid,
                    'status': 'SUCCESS',
                    'timestamp': datetime.now().isoformat()
                })
                storage_path = self.config.get('move_destination', {}).get('storage_path', 'Unknown')
                self.logger.info(f"C-MOVE request sent successfully for study {study_uid}")
                self.logger.info(f"Study should be available at: {storage_path}")
            else:
                failed_studies.append(study_uid)
                if record_failure:
                    self.failed_downloads.append({
                        'patient_id': patient_id,
                        'date': study_date,
                        'modality': modality,
                        'server': server_name,
                        'reason': f'C-MOVE failed for study {study_uid}',
                        'timestamp': datetime.now().isoformat()
                    })
                all_successful = False

        if all_successful and studies_moved:
            self.successful_downloads.append({
                'patient_id': patient_id,
                'date': study_date,
                'modality': modality,
                'server': server_name,
                'studies': studies_moved,
                'timestamp': datetime.now().isoformat()
            })

        if not all_successful:
            reason = f"C-MOVE failed for {len(failed_studies)} of {len(studies)} studies"
            return False, reason

        return True, None

    def process_batch(
        self,
        csv_file,
        lookup_servers: Optional[List[str]] = None,
        alt_modalities: Optional[List[str]] = None
    ):
        """Process batch queries from CSV file"""
        self.logger.info(f"Processing batch file: {csv_file}")

        def normalize_key(key: str) -> str:
            return ''.join(key.split()).lower()

        def get_field(row: Dict, *candidates: str) -> Optional[str]:
            for candidate in candidates:
                if not candidate:
                    continue
                value = row.get(candidate)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return None

        try:
            with open(csv_file, 'r', newline='') as f:
                first_line = f.readline()
                f.seek(0)
                header_line = normalize_key(first_line.lstrip('\ufeff'))
                has_header = any(token in header_line for token in (
                    'patientid', 'patient_id', 'studydate', 'study_date', 'date', 'modality', 'server'
                ))

                if has_header:
                    reader = csv.DictReader(f)
                    normalized_fields = {}
                    for field in reader.fieldnames or []:
                        if field is None:
                            continue
                        normalized_fields[normalize_key(field)] = field

                    for row in reader:
                        if not row:
                            continue
                        raw_patient = get_field(
                            row,
                            normalized_fields.get('patientid'),
                            normalized_fields.get('patient_id'),
                            normalized_fields.get('patient'),
                            normalized_fields.get('id')
                        )
                        if raw_patient and raw_patient.startswith('#'):
                            continue

                        patient_id = raw_patient
                        study_date = get_field(
                            row,
                            normalized_fields.get('studydate'),
                            normalized_fields.get('study_date'),
                            normalized_fields.get('date')
                        )
                        modality = get_field(row, normalized_fields.get('modality'))
                        server = get_field(row, normalized_fields.get('server'))

                        if not all([patient_id, study_date, modality]):
                            self.logger.warning(f"Skipping row with missing fields: {row}")
                            continue

                        if not server and not lookup_servers:
                            self.logger.warning(f"Skipping row with missing server: {row}")
                            continue

                        self.process_query_with_inline_server(
                            patient_id,
                            study_date,
                            modality,
                            server,
                            lookup_servers=lookup_servers,
                            alt_modalities=alt_modalities
                        )
                else:
                    reader = csv.reader(f, skipinitialspace=True)
                    for row in reader:
                        # Skip comments and empty lines
                        if not row or str(row[0]).strip().startswith('#'):
                            continue

                        if len(row) < 3:
                            self.logger.warning(f"Invalid row format: {row}")
                            continue

                        patient_id, study_date, modality = [x.strip() for x in row[:3]]
                        server = row[3].strip() if len(row) > 3 else None

                        if not server and not lookup_servers:
                            self.logger.warning(f"Skipping row with missing server: {row}")
                            continue

                        self.process_query_with_inline_server(
                            patient_id,
                            study_date,
                            modality,
                            server,
                            lookup_servers=lookup_servers,
                            alt_modalities=alt_modalities
                        )

        except Exception as e:
            self.logger.error(f"Error processing batch file: {e}")

    def generate_report(self):
        """Generate failure report"""
        report_file = f"dicom_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        with open(report_file, 'w') as f:
            f.write("=" * 50 + "\n")
            f.write("DICOM DOWNLOAD REPORT\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write("=" * 50 + "\n\n")

            # Summary
            total = len(self.successful_downloads) + len(self.failed_downloads)
            if total > 0:
                success_rate = (len(self.successful_downloads) / total) * 100
                f.write(f"Total Queries: {total}\n")
                f.write(f"Successful: {len(self.successful_downloads)}\n")
                f.write(f"Failed: {len(self.failed_downloads)}\n")
                f.write(f"Success Rate: {success_rate:.1f}%\n")
                f.write(f"Total C-MOVE Requests: {len(self.move_requests)}\n\n")

                # Get storage path from config
                storage_path = self.config.get('move_destination', {}).get('storage_path', 'Unknown')
                destination_ae = self.config.get('move_destination', {}).get('ae_title', 'Unknown')

                f.write(f"NOTE: Studies are sent to AE Title '{destination_ae}'\n")
                f.write(f"      Storage location: {storage_path}\n\n")

            # Failed downloads
            if self.failed_downloads:
                f.write("FAILED DOWNLOADS:\n")
                f.write("-" * 50 + "\n")
                for i, failure in enumerate(self.failed_downloads, 1):
                    f.write(f"\n{i}. Patient: {failure['patient_id']}, ")
                    f.write(f"Date: {failure['date']}, ")
                    f.write(f"Modality: {failure['modality']}, ")
                    f.write(f"Server: {failure['server']}\n")
                    f.write(f"   Reason: {failure['reason']}\n")
                    f.write(f"   Time: {failure['timestamp']}\n")

            # Successful downloads
            if self.successful_downloads:
                f.write("\n\nSUCCESSFUL DOWNLOADS:\n")
                f.write("-" * 50 + "\n")
                for i, success in enumerate(self.successful_downloads, 1):
                    f.write(f"\n{i}. Patient: {success['patient_id']}, ")
                    f.write(f"Date: {success['date']}, ")
                    f.write(f"Modality: {success['modality']}, ")
                    f.write(f"Server: {success['server']}\n")
                    f.write(f"   Studies: {', '.join(success.get('studies', []))}\n")
                    f.write(f"   Time: {success['timestamp']}\n")

        self.logger.info(f"Report saved to: {report_file}")
        return report_file

    def parse_server_info(self, server_string):
        """Parse server information from various text formats"""
        server_info = {}

        # Remove extra whitespace and normalize
        server_string = ' '.join(server_string.split())

        # Pattern 1: "Name: Host 10.x.x.x AE Title XXX Port 104"
        pattern1 = r'(?:Host|IP)[:\s]+([0-9.]+).*?(?:AE|Title)[:\s]+([\w]+).*?Port[:\s]+(\d+)'

        # Pattern 2: "10.x.x.x XXX 104" (IP, AE Title, Port)
        pattern2 = r'^([0-9.]+)\s+([\w]+)\s+(\d+)$'

        # Pattern 3: Key-value pairs
        pattern3 = r'(ip|host|ae_title|aetitle|port)[:\s]+([\w.]+)'

        # Try pattern 1
        match = re.search(pattern1, server_string, re.IGNORECASE)
        if match:
            server_info['ip'] = match.group(1)
            server_info['ae_title'] = match.group(2)
            server_info['port'] = int(match.group(3))
            return server_info

        # Try pattern 2
        match = re.match(pattern2, server_string.strip())
        if match:
            server_info['ip'] = match.group(1)
            server_info['ae_title'] = match.group(2)
            server_info['port'] = int(match.group(3))
            return server_info

        # Try pattern 3 (key-value pairs)
        matches = re.findall(pattern3, server_string, re.IGNORECASE)
        if matches:
            for key, value in matches:
                key = key.lower()
                if key in ['ip', 'host']:
                    server_info['ip'] = value
                elif key in ['ae_title', 'aetitle']:
                    server_info['ae_title'] = value
                elif key == 'port':
                    server_info['port'] = int(value)

        return server_info if all(k in server_info for k in ['ip', 'ae_title', 'port']) else None

    def add_server(self, name, server_info, save=True):
        """Add a new server configuration"""
        # Add to current config
        self.config['servers'][name] = {
            'port': server_info['port'],
            'ip': server_info['ip'],
            'ae_title': server_info['ae_title'],
            'description': server_info.get('description', f'{name} PACS Server')
        }

        if save:
            # Save to additional servers file
            additional_servers_file = Path('additional_servers.json')
            additional_servers = {}

            if additional_servers_file.exists():
                try:
                    with open(additional_servers_file, 'r') as f:
                        additional_servers = json.load(f)
                except:
                    pass

            additional_servers[name] = self.config['servers'][name]

            with open(additional_servers_file, 'w') as f:
                json.dump(additional_servers, f, indent=2)

            self.logger.info(f"Added server '{name}' to configuration")

        return True

    def process_query_with_inline_server(
        self,
        patient_id,
        study_date,
        modality,
        server_spec: Optional[str],
        lookup_servers: Optional[List[str]] = None,
        alt_modalities: Optional[List[str]] = None
    ):
        """Process query with inline server specification"""
        server_name = None
        if server_spec:
            # Check if server_spec contains inline server info (has | separator)
            if '|' in server_spec:
                parts = server_spec.split('|')
                if len(parts) >= 4:
                    server_name = parts[0].strip()
                    server_info = {
                        'ip': parts[1].strip(),
                        'ae_title': parts[2].strip(),
                        'port': int(parts[3].strip())
                    }
                    # Add server temporarily (don't save)
                    self.add_server(server_name, server_info, save=False)
            else:
                server_name = server_spec.strip()

        return self.process_query_with_lookup(
            patient_id,
            study_date,
            modality,
            server_name,
            lookup_servers=lookup_servers,
            alt_modalities=alt_modalities
        )


def main():
    parser = argparse.ArgumentParser(description='DICOM Download Tool')
    parser.add_argument('--config', default='config.yaml', help='Configuration file')
    parser.add_argument('--batch', help='Process batch CSV file')
    parser.add_argument('--id', help='Patient ID')
    parser.add_argument('--date', help='Study date (YYYY-MM-DD)')
    parser.add_argument('--modality', help='Modality (CT, MR, MG, etc.)')
    parser.add_argument('--server', help='Server name from config')
    parser.add_argument(
        '--lookup',
        nargs='+',
        help='Try fallback servers in order. Use "all" or list servers (e.g. --lookup LK TY).'
    )
    parser.add_argument(
        '--alt-modality',
        nargs='+',
        help='Fallback modality values to try in order (e.g. --alt-modality CR US).'
    )
    parser.add_argument('--timeout', type=int, help='Override download timeout (seconds)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--add-server', help='Add server (format: "Name:IP:AETitle:Port" or paste server info)')
    parser.add_argument('--list-servers', action='store_true', help='List all configured servers')
    parser.add_argument('--parse-servers', help='Parse servers from text file')

    args = parser.parse_args()

    # Initialize downloader
    downloader = DICOMDownloader(args.config)

    # Override timeout if specified
    if args.timeout:
        downloader.config['settings']['download_timeout'] = args.timeout

    # Enable debug mode if requested
    if args.debug:
        downloader.logger.setLevel(logging.DEBUG)
        from pynetdicom import debug_logger
        debug_logger()

    # Handle server management commands
    if args.list_servers:
        print("\nConfigured DICOM Servers:")
        print("=" * 60)
        for name, config in downloader.config['servers'].items():
            print(f"\n{name}:")
            print(f"  IP: {config['ip']}")
            print(f"  AE Title: {config['ae_title']}")
            print(f"  Port: {config['port']}")
            print(f"  Description: {config.get('description', 'N/A')}")
        sys.exit(0)

    if args.add_server:
        # Parse server info
        if ':' in args.add_server and args.add_server.count(':') >= 3:
            # Format: Name:IP:AETitle:Port
            parts = args.add_server.split(':')
            name = parts[0]
            server_info = {
                'ip': parts[1],
                'ae_title': parts[2],
                'port': int(parts[3])
            }
        else:
            # Try to parse from text format
            server_info = downloader.parse_server_info(args.add_server)
            if not server_info:
                print("Error: Could not parse server information")
                print("Use format: Name:IP:AETitle:Port or provide full server details")
                sys.exit(1)
            name = input("Enter server name: ").strip()

        if downloader.add_server(name, server_info):
            print(f"Successfully added server '{name}'")
        sys.exit(0)

    if args.parse_servers:
        # Parse servers from text file
        try:
            with open(args.parse_servers, 'r') as f:
                content = f.read()

            # Try to parse each line as a server
            lines = content.strip().split('\n')
            servers_added = 0

            for line in lines:
                if not line.strip() or line.startswith('#'):
                    continue

                # Check if line has server name at the beginning
                if ':' in line or 'Host' in line or re.match(r'^[A-Z]{2}\s', line):
                    # Extract server name if present
                    name_match = re.match(r'^([A-Z]{2,})\s*[:]*\s*(.+)$', line)
                    if name_match:
                        name = name_match.group(1)
                        server_string = name_match.group(2)
                    else:
                        server_string = line
                        name = input(f"Enter name for server ({line[:30]}...): ").strip()

                    server_info = downloader.parse_server_info(server_string)
                    if server_info:
                        downloader.add_server(name, server_info)
                        servers_added += 1
                        print(f"Added server '{name}'")

            print(f"\nSuccessfully added {servers_added} servers")
        except Exception as e:
            print(f"Error parsing servers file: {e}")
        sys.exit(0)

    # Process queries
    if args.batch:
        downloader.process_batch(
            args.batch,
            lookup_servers=args.lookup,
            alt_modalities=args.alt_modality
        )
    elif args.id and args.date and args.modality and (args.server or args.lookup):
        downloader.process_query_with_lookup(
            args.id,
            args.date,
            args.modality,
            args.server,
            lookup_servers=args.lookup,
            alt_modalities=args.alt_modality
        )
    else:
        # Interactive mode
        print("\n" + "=" * 50)
        print("DICOM DOWNLOAD TOOL - Interactive Mode")
        print("=" * 50)
        print("\nAvailable servers:")
        for name, config in downloader.config['servers'].items():
            print(f"  {name}: {config['description']}")

        print("\nEnter query details (or 'quit' to exit):")
        if args.lookup:
            print(f"Lookup enabled (servers): {', '.join(args.lookup)}")
        if args.alt_modality:
            print(f"Lookup enabled (modalities): {', '.join(args.alt_modality)}")

        while True:
            try:
                patient_id = input("\nPatient ID: ").strip()
                if patient_id.lower() == 'quit':
                    break

                study_date = input("Study Date (YYYY-MM-DD): ").strip()
                modality = input("Modality (CT/MR/MG/etc.): ").strip().upper()
                server = input("Server name: ").strip()
                if not server:
                    if not args.lookup:
                        print("Server name is required unless --lookup is specified.")
                        continue
                    server = None

                downloader.process_query_with_lookup(
                    patient_id,
                    study_date,
                    modality,
                    server,
                    lookup_servers=args.lookup,
                    alt_modalities=args.alt_modality
                )

                another = input("\nProcess another query? (y/n): ").strip().lower()
                if another != 'y':
                    break

            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break

    # Generate report
    if downloader.failed_downloads or downloader.successful_downloads:
        report_file = downloader.generate_report()
        print(f"\nReport saved to: {report_file}")

    print("\nDone!")


if __name__ == '__main__':
    main()
