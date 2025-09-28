#!/usr/bin/env python3
"""
Package Verification Script
Tests that all required packages are properly installed and accessible
"""

import sys
import os

def test_imports():
    """Test if all required packages can be imported"""
    print("=" * 60)
    print("DICOM Download Tool - Package Verification")
    print("=" * 60)
    print()

    packages = [
        ('yaml', 'PyYAML'),
        ('pydicom', 'pydicom'),
        ('pynetdicom', 'pynetdicom'),
        ('csv', 'csv (built-in)'),
        ('pathlib', 'pathlib (built-in)'),
        ('argparse', 'argparse (built-in)'),
        ('logging', 'logging (built-in)'),
        ('threading', 'threading (built-in)'),
        ('datetime', 'datetime (built-in)'),
        ('re', 're (built-in)'),
        ('json', 'json (built-in)')
    ]

    all_ok = True

    for module_name, display_name in packages:
        try:
            __import__(module_name)
            print(f"✓ {display_name:<25} - OK")
        except ImportError as e:
            print(f"✗ {display_name:<25} - FAILED: {e}")
            all_ok = False

    print()
    print("=" * 60)

    if all_ok:
        print("SUCCESS: All required packages are available!")
        print()
        print("Testing DICOM-specific imports...")

        try:
            from pynetdicom import AE
            from pydicom.dataset import Dataset
            print("✓ Core DICOM classes imported successfully")

            # Test configuration loading
            import yaml
            print("✓ YAML configuration loading available")

            print()
            print("The tool is ready to use!")

        except Exception as e:
            print(f"✗ Error testing DICOM functionality: {e}")
            return False
    else:
        print("ERROR: Some packages are missing!")
        print()
        print("Please ensure all packages are in the lib/ folder")
        print("and run setup_windows.bat on Windows")
        return False

    return True

def check_config():
    """Check if configuration file exists and is valid"""
    print()
    print("Checking configuration...")

    config_file = 'config.yaml'
    if os.path.exists(config_file):
        print(f"✓ {config_file} found")

        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # Check for required sections
            required_sections = ['settings', 'servers', 'local_ae']
            for section in required_sections:
                if section in config:
                    print(f"  ✓ '{section}' section present")
                else:
                    print(f"  ✗ '{section}' section missing")

            # List configured servers
            if 'servers' in config:
                print()
                print("Configured servers:")
                for name in config['servers']:
                    server = config['servers'][name]
                    print(f"  - {name}: {server.get('ip', 'NO IP')} ({server.get('ae_title', 'NO AE')})")

        except Exception as e:
            print(f"✗ Error reading configuration: {e}")
    else:
        print(f"✗ {config_file} not found")

if __name__ == "__main__":
    success = test_imports()

    if success:
        check_config()

    print()
    print("=" * 60)
    print("Press Enter to continue...")
    input()