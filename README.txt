================================================================================
                        DICOM DOWNLOAD TOOL - README
================================================================================

OVERVIEW
--------
This tool downloads DICOM images from PACS servers using patient ID, study date,
and modality. It supports multiple servers and includes timeout handling to skip
problematic downloads.


INSTALLATION
------------
1. Unzip the FuDownload folder to any location on your Windows computer
2. No installation required - the tool is ready to use immediately
3. All Python dependencies are included in the package


CONFIGURATION
-------------
1. Edit config.yaml to add your DICOM servers:
   - ae_title: The Application Entity title of the PACS server
   - ip: Server IP address
   - port: Server port (usually 11112)
   - description: Friendly name for the server

2. Adjust timeout settings in config.yaml if needed:
   - query_timeout: Maximum time for C-FIND queries (default: 30 seconds)
   - download_timeout: Maximum time for C-MOVE downloads (default: 120 seconds)


USAGE
-----

1. BATCH PROCESSING (Recommended)
   Edit queries.csv with your patient list, then run:
   > run.bat --batch queries.csv

   CSV Format (NO header row required):
   Column 1: PatientID (e.g., 8318169 or PAT001)
   Column 2: Date in YYYY-MM-DD format (e.g., 2025-09-22)
   Column 3: Modality (e.g., CT, MR, US)
   Column 4: Server name from config.yaml (e.g., LK, LNK)

   Examples:
   8318169, 2019-05-20, CT, LK
   PAT001, 2025-09-22, MR, LNK
   12345, 2025-09-21, US, LK

   Note: Lines starting with # are treated as comments and ignored


2. SINGLE QUERY
   > run.bat --id PAT001 --date 2025-09-22 --modality CT --server LNK


3. INTERACTIVE MODE
   > run.bat
   Follow the prompts to enter query details


4. ADVANCED OPTIONS
   --timeout 180     Override download timeout (in seconds)
   --debug          Enable detailed debug logging
   --config alt.yaml Use alternative config file


OUTPUT
------
- Downloaded DICOM files are saved in: downloads\SERVER\DATE_PATIENTID_MODALITY\
- Logs are saved in: logs\
- Failed downloads report: failed_downloads_TIMESTAMP.txt


TROUBLESHOOTING
---------------
1. Connection Failed:
   - Verify server IP and port in config.yaml
   - Check network connectivity
   - Ensure PACS server has your AE title configured

2. No Studies Found:
   - Verify patient ID format matches PACS system
   - Check date format (YYYY-MM-DD)
   - Confirm modality abbreviation (CT, MR, MG, etc.)

3. Download Timeout:
   - Large studies may need longer timeout (use --timeout option)
   - Check network speed
   - Verify PACS server performance

4. Missing Files:
   - Check failed_downloads report for details
   - Verify sufficient disk space
   - Check folder permissions


SERVER CONFIGURATION
--------------------
Your PACS administrator needs to:
1. Add "DICOM_DOWNLOADER" as an allowed AE title
2. Configure it to accept connections from your IP
3. Enable Query/Retrieve services


ADDING NEW SERVERS
------------------
Edit config.yaml and add new server entry:

servers:
  NEW_SERVER:
    ae_title: "NEW_PACS"
    ip: "192.168.x.x"
    port: 11112
    description: "New Hospital PACS"


LOG FILES
---------
Logs contain:
- Connection attempts
- Query parameters
- Download progress
- Error messages
- Timeout events

Check logs in the logs\ folder for debugging.


FAILED DOWNLOADS REPORT
-----------------------
After each run, a report is generated listing:
- Successfully downloaded studies
- Failed downloads with reasons
- Timeout failures for manual handling
- Overall success rate


NOTES
-----
- The tool automatically retries failed connections (configurable)
- Downloads that timeout after 2 minutes are skipped
- All DICOM files are saved with their SOP Instance UID
- The tool supports CT, MR, MG, and other DICOM modalities


SUPPORT
-------
For issues:
1. Check the log files in logs\ folder
2. Review the failed_downloads report
3. Verify server configuration with PACS administrator
4. Ensure network connectivity


================================================================================