import argparse
import csv
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


DEFAULT_CLEAR_PATH = r"C:\RA600\DATABASE\LOCAL\general"
DEFAULT_BATCH_SIZE = 20
DEFAULT_TRANSFER_ROOT = r"C:\FuTransfer"
DEFAULT_TRANSFER_PORT = 443
DEFAULT_ZIP_ROOT = "transfer_zips"


def load_storage_path(config_path):
    try:
        import yaml
    except Exception:
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        move_cfg = data.get("move_destination", {})
        storage_path = move_cfg.get("storage_path")
        if storage_path:
            return str(storage_path)
    except Exception:
        return None
    return None


def normalize_key(key):
    return "".join(str(key).split()).lower()


def get_field(row, *candidates):
    for candidate in candidates:
        if not candidate:
            continue
        value = row.get(candidate)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def parse_case_list(csv_path):
    tokens = (
        "patientid",
        "patient_id",
        "studydate",
        "study_date",
        "date",
        "modality",
        "server",
    )

    with open(csv_path, "r", newline="", encoding="utf-8") as handle:
        first_line = handle.readline()
        handle.seek(0)
        header_line = normalize_key(first_line.lstrip("\ufeff"))
        has_header = any(token in header_line for token in tokens)

        if has_header:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            normalized_fields = {}
            for field in fieldnames:
                if field is None:
                    continue
                normalized_fields[normalize_key(field)] = field

            rows = []
            skipped = 0
            for row in reader:
                if not row:
                    continue
                raw_patient = get_field(
                    row,
                    normalized_fields.get("patientid"),
                    normalized_fields.get("patient_id"),
                    normalized_fields.get("patient"),
                    normalized_fields.get("id"),
                )
                if raw_patient and raw_patient.startswith("#"):
                    continue

                patient_id = raw_patient
                study_date = get_field(
                    row,
                    normalized_fields.get("studydate"),
                    normalized_fields.get("study_date"),
                    normalized_fields.get("date"),
                )
                modality = get_field(row, normalized_fields.get("modality"))
                server = get_field(row, normalized_fields.get("server"))

                if not all([patient_id, study_date, modality, server]):
                    skipped += 1
                    continue

                rows.append(row)

            return {
                "has_header": True,
                "fieldnames": fieldnames,
                "rows": rows,
                "skipped": skipped,
            }

        reader = csv.reader(handle, skipinitialspace=True)
        rows = []
        skipped = 0
        for row in reader:
            if not row or str(row[0]).strip().startswith("#"):
                continue
            if len(row) < 4:
                skipped += 1
                continue
            rows.append(row)

        return {
            "has_header": False,
            "fieldnames": None,
            "rows": rows,
            "skipped": skipped,
        }


def is_drive_root(path):
    resolved = Path(path).resolve()
    parts = resolved.parts
    if os.name == "nt":
        return len(parts) == 1 and parts[0].endswith(":\\")
    return resolved == Path("/")


def clear_directory_contents(path, dry_run=False):
    target = Path(path)
    if not target.exists():
        print(f"[clear] Skip missing path: {target}")
        return False
    if is_drive_root(target):
        print(f"[clear] Refusing to clear drive root: {target}")
        return False

    ok = True
    for entry in target.iterdir():
        try:
            if dry_run:
                print(f"[clear] {entry}")
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        except Exception as exc:
            ok = False
            print(f"[clear] Failed to remove {entry}: {exc}")
    return ok


def collect_csvs(inputs, recursive=False):
    csv_files = []
    errors = []
    seen = set()

    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            pattern = "**/*.csv" if recursive else "*.csv"
            for csv_path in sorted(path.glob(pattern)):
                if csv_path.is_file():
                    resolved = str(csv_path.resolve())
                    if resolved not in seen:
                        csv_files.append(csv_path)
                        seen.add(resolved)
        elif path.is_file() and path.suffix.lower() == ".csv":
            resolved = str(path.resolve())
            if resolved not in seen:
                csv_files.append(path)
                seen.add(resolved)
        else:
            errors.append(raw)

    return csv_files, errors


def resolve_path(path_value, script_dir):
    path = Path(path_value)
    if not path.is_absolute():
        path = script_dir / path
    return path


def resolve_transfer_root(preferred_root, script_dir):
    preferred = Path(preferred_root)
    if preferred.exists():
        return preferred
    sibling = Path(script_dir).parent / "FuTransfer"
    if sibling.exists():
        return sibling
    return preferred


def extract_config_path(download_args, script_dir):
    if not download_args:
        return None

    for idx, arg in enumerate(download_args):
        if arg == "--config" and idx + 1 < len(download_args):
            return Path(download_args[idx + 1])
        if arg.startswith("--config="):
            return Path(arg.split("=", 1)[1])

    return None


def build_transfer_args(args, folder):
    if not args.transfer_server:
        return None, "Missing --transfer-server (or set FUTRANSFER_SERVER)."

    transfer_args = [
        "--server",
        args.transfer_server,
        "--port",
        str(args.transfer_port),
        "--folder",
        str(folder),
    ]

    if args.transfer_legacy:
        transfer_args.append("--legacy-protocol")
    if args.transfer_no_resume:
        transfer_args.append("--no-resume")
    if args.transfer_clear_state:
        transfer_args.append("--clear-state")
    if args.transfer_compression:
        transfer_args.extend(["--compression", args.transfer_compression])

    return transfer_args, None


def write_chunk_csv(path, chunk, has_header, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        if has_header:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in chunk:
                writer.writerow(row)
        else:
            writer = csv.writer(handle)
            writer.writerows(chunk)


def zip_storage_contents(storage_path, zip_path, dry_run=False):
    storage = Path(storage_path)
    if dry_run:
        print(f"[zip] {storage} -> {zip_path} (dry-run)")
        return True

    if not storage.exists():
        print(f"[zip] Missing storage path: {storage}")
        return False

    files = []
    for root, _, filenames in os.walk(storage):
        for filename in filenames:
            file_path = Path(root) / filename
            rel_path = file_path.relative_to(storage)
            files.append((file_path, rel_path))

    if not files:
        print(f"[zip] No files found under {storage}")
        return False

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
        for file_path, rel_path in files:
            zip_handle.write(file_path, rel_path.as_posix())

    return True


def chunk_rows(rows, batch_size):
    for start in range(0, len(rows), batch_size):
        batch_index = start // batch_size + 1
        yield batch_index, rows[start : start + batch_size]


def run_cmd(cmd, cwd, dry_run=False):
    print(f"[run] {cmd}")
    if dry_run:
        return 0
    completed = subprocess.run(cmd, cwd=cwd)
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Batch wrapper: download in chunks, zip RA600 storage, clear, then transfer."
        ),
        epilog="Extra arguments are passed to dicom_downloader (e.g., --timeout 180).",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="CSV file(s) or folders containing CSV files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search CSV files recursively in provided folders.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Cases per download batch (default: 20).",
    )
    parser.add_argument(
        "--transfer-server",
        default=os.getenv("FUTRANSFER_SERVER"),
        help="FuTransfer server IP (or set FUTRANSFER_SERVER).",
    )
    parser.add_argument(
        "--transfer-port",
        type=int,
        default=DEFAULT_TRANSFER_PORT,
        help="FuTransfer server port.",
    )
    parser.add_argument(
        "--transfer-folder",
        help="Zip staging root for transfer (overrides --zip-root).",
    )
    parser.add_argument(
        "--transfer-root",
        default=DEFAULT_TRANSFER_ROOT,
        help="FuTransfer folder (default: C:\\FuTransfer).",
    )
    parser.add_argument(
        "--transfer-legacy",
        action="store_true",
        help="Use legacy protocol for FuTransfer.",
    )
    parser.add_argument(
        "--transfer-no-resume",
        action="store_true",
        help="Disable resume for legacy protocol.",
    )
    parser.add_argument(
        "--transfer-clear-state",
        action="store_true",
        help="Clear FuTransfer resume state before transfer.",
    )
    parser.add_argument(
        "--transfer-compression",
        choices=["gz", "none"],
        help="Compression for FuTransfer batch mode.",
    )
    parser.add_argument(
        "--zip-root",
        default=DEFAULT_ZIP_ROOT,
        help="Folder for batch zip files (default: transfer_zips).",
    )
    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Keep zip files after a successful transfer.",
    )
    parser.add_argument(
        "--clear-path",
        help="Path to clear before transfer (default: move_destination storage_path).",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Skip clearing the storage folder before transfer.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop on first download/transfer failure.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )

    args, download_args = parser.parse_known_args()

    if args.batch_size <= 0:
        print("Invalid --batch-size (must be > 0).")
        return 1

    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "config.yaml"
    override_config = extract_config_path(download_args, script_dir)
    if override_config:
        config_path = (script_dir / override_config).resolve()
    storage_path = load_storage_path(config_path) or DEFAULT_CLEAR_PATH
    clear_path = args.clear_path or storage_path
    zip_root_input = args.transfer_folder or args.zip_root
    zip_root = resolve_path(zip_root_input, script_dir)
    transfer_root = resolve_transfer_root(args.transfer_root, script_dir)

    csv_files, errors = collect_csvs(args.inputs, recursive=args.recursive)
    if errors:
        print("Invalid CSV inputs:")
        for entry in errors:
            print(f"  - {entry}")
        return 1
    if not csv_files:
        print("No CSV files found.")
        return 1

    if not args.transfer_server:
        print("Missing --transfer-server (or set FUTRANSFER_SERVER).")
        return 1

    run_bat = script_dir / "run.bat"
    if not run_bat.exists():
        print(f"Missing run.bat at {run_bat}")
        return 1

    run_client = transfer_root / "run_client.bat"
    if not run_client.exists():
        print(f"Missing FuTransfer client at {run_client}")
        return 1

    if os.name != "nt":
        print("Warning: This wrapper is intended for Windows (.bat execution).")

    overall_ok = True
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = script_dir / "batch_tmp" / run_id

    for csv_file in csv_files:
        print(f"=== Processing {csv_file} ===")
        case_data = parse_case_list(csv_file)
        rows = case_data["rows"]
        skipped = case_data["skipped"]
        if skipped:
            print(f"[batch] Skipped {skipped} invalid rows.")
        if not rows:
            print("[batch] No valid cases found.")
            continue

        temp_dir = temp_root / csv_file.stem
        temp_dir.mkdir(parents=True, exist_ok=True)
        total_batches = (len(rows) + args.batch_size - 1) // args.batch_size
        print(f"[batch] {len(rows)} cases -> {total_batches} batch(es)")

        for batch_index, chunk in chunk_rows(rows, args.batch_size):
            print(f"[batch] Starting {batch_index}/{total_batches}")
            temp_csv = temp_dir / f"{csv_file.stem}_batch{batch_index:03d}.csv"
            if not args.dry_run:
                write_chunk_csv(
                    temp_csv,
                    chunk,
                    case_data["has_header"],
                    case_data["fieldnames"],
                )

            download_cmd = ["cmd", "/c", str(run_bat), "--batch", str(temp_csv)]
            download_cmd.extend(download_args)
            download_rc = run_cmd(download_cmd, cwd=str(script_dir), dry_run=args.dry_run)
            if download_rc != 0:
                overall_ok = False
                print(f"[download] Failed with code {download_rc}")
                if args.stop_on_error:
                    break

            batch_dir = zip_root / f"{csv_file.stem}_batch{batch_index:03d}_{run_id}"
            zip_path = batch_dir / f"{csv_file.stem}_batch{batch_index:03d}.zip"
            zipped = zip_storage_contents(clear_path, zip_path, dry_run=args.dry_run)
            if not zipped:
                overall_ok = False
                print("[zip] Failed to create zip. Skipping transfer.")
                if args.stop_on_error:
                    break
                continue

            if not args.no_clear:
                cleared = clear_directory_contents(clear_path, dry_run=args.dry_run)
                if not cleared:
                    overall_ok = False
                    print("[clear] Completed with errors.")
                    if args.stop_on_error:
                        break

            transfer_args, transfer_err = build_transfer_args(args, batch_dir)
            if transfer_err:
                print(transfer_err)
                return 1

            transfer_cmd = ["cmd", "/c", str(run_client)]
            transfer_cmd.extend(transfer_args)
            transfer_rc = run_cmd(transfer_cmd, cwd=str(transfer_root), dry_run=args.dry_run)
            if transfer_rc != 0:
                overall_ok = False
                print(f"[transfer] Failed with code {transfer_rc}")
                if args.stop_on_error:
                    break
            else:
                if not args.keep_zip and not args.dry_run:
                    try:
                        zip_path.unlink()
                        if batch_dir.exists() and not any(batch_dir.iterdir()):
                            batch_dir.rmdir()
                    except Exception as exc:
                        overall_ok = False
                        print(f"[zip] Failed to remove {zip_path}: {exc}")
                        if args.stop_on_error:
                            break

            if not args.dry_run:
                try:
                    temp_csv.unlink()
                except Exception:
                    pass

        if args.stop_on_error and not overall_ok:
            break

    if not args.dry_run and temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
