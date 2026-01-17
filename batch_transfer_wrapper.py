import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

try:
    from download_monitor import DownloadMonitor
except Exception:
    DownloadMonitor = None

DEFAULT_CLEAR_PATH = r"C:\RA600\DATABASE\LOCAL\general"
DEFAULT_BATCH_SIZE = 20
DEFAULT_TRANSFER_ROOT = r"C:\FuTransfer"
DEFAULT_TRANSFER_PORT = None
DEFAULT_TRANSFER_MODE = "zip"
DEFAULT_TRANSFER_PROTOCOL = "http"
DEFAULT_ZIP_ROOT = "transfer_zips"
DEFAULT_TMP_CLEANUP_HOURS = 24
DEFAULT_ZIP_CLEANUP_HOURS = 0
DEFAULT_CLEANUP_INTERVAL_MINUTES = 10
DEFAULT_MONITOR_HOST = "0.0.0.0"
DEFAULT_MONITOR_PORT = 8081


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


def has_any_files(path, dry_run=False):
    target = Path(path)
    if dry_run:
        print(f"[transfer] {target} (dry-run)")
        return True
    if not target.exists():
        print(f"[transfer] Missing source path: {target}")
        return False
    for root, _, filenames in os.walk(target):
        if filenames:
            return True
    print(f"[transfer] No files found under {target}")
    return False


def cleanup_old_entries(root, max_age_seconds, dry_run=False, label=None):
    target = Path(root)
    if not target.exists():
        return 0

    now = time.time()
    removed = 0

    for entry in target.iterdir():
        try:
            age_seconds = now - entry.stat().st_mtime
        except OSError:
            continue
        if age_seconds < max_age_seconds:
            continue
        if dry_run:
            print(f"[cleanup] {entry}")
            removed += 1
            continue
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed += 1
        except Exception as exc:
            print(f"[cleanup] Failed to remove {entry}: {exc}")

    if removed:
        label = label or str(target)
        print(f"[cleanup] Removed {removed} item(s) from {label}")

    return removed


def maybe_run_cleanup(last_cleanup, interval_seconds, tmp_root, zip_root, tmp_ttl, zip_ttl, dry_run=False):
    if interval_seconds <= 0:
        return last_cleanup

    now = time.time()
    if last_cleanup and (now - last_cleanup) < interval_seconds:
        return last_cleanup

    if tmp_ttl > 0:
        cleanup_old_entries(tmp_root, tmp_ttl, dry_run=dry_run, label="batch_tmp")
    if zip_ttl > 0:
        cleanup_old_entries(zip_root, zip_ttl, dry_run=dry_run, label="transfer_zips")

    return now


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
        "--folder",
        str(folder),
    ]

    if args.transfer_protocol == "http":
        transfer_args.append("--http")
    if args.transfer_port is not None:
        transfer_args.extend(["--port", str(args.transfer_port)])
    if args.transfer_legacy:
        print("[transfer] Warning: --transfer-legacy is deprecated and ignored.")
    if args.transfer_protocol == "http":
        if args.transfer_no_resume:
            transfer_args.append("--no-resume")
        if args.transfer_clear_state:
            transfer_args.append("--clear-state")
        if args.transfer_compression:
            print("[transfer] Warning: --transfer-compression ignored in HTTP mode.")
    else:
        if args.transfer_no_resume or args.transfer_clear_state:
            print("[transfer] Warning: --transfer-no-resume/--transfer-clear-state only apply to HTTP mode.")
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
        "--transfer-mode",
        choices=["zip", "direct"],
        default=DEFAULT_TRANSFER_MODE,
        help="Transfer mode: zip (default) or direct.",
    )
    parser.add_argument(
        "--transfer-http",
        action="store_true",
        help="Deprecated: use --transfer-protocol http.",
    )
    parser.add_argument(
        "--transfer-protocol",
        choices=["http", "batch"],
        default=DEFAULT_TRANSFER_PROTOCOL,
        help="FuTransfer protocol (default: http).",
    )
    parser.add_argument(
        "--transfer-port",
        type=int,
        default=DEFAULT_TRANSFER_PORT,
        help="FuTransfer server port (default: 8080 for HTTP, 443 for batch).",
    )
    parser.add_argument(
        "--transfer-folder",
        help="Zip staging root for transfer (zip mode, overrides --zip-root).",
    )
    parser.add_argument(
        "--transfer-root",
        default=DEFAULT_TRANSFER_ROOT,
        help="FuTransfer folder (default: C:\\FuTransfer).",
    )
    parser.add_argument(
        "--transfer-legacy",
        action="store_true",
        help="Deprecated: legacy protocol flag (ignored).",
    )
    parser.add_argument(
        "--transfer-no-resume",
        action="store_true",
        help="Disable resume for FuTransfer HTTP mode.",
    )
    parser.add_argument(
        "--transfer-clear-state",
        action="store_true",
        help="Clear FuTransfer resume state before transfer (HTTP mode).",
    )
    parser.add_argument(
        "--transfer-compression",
        choices=["gz", "none"],
        help="Compression for FuTransfer batch mode.",
    )
    parser.add_argument(
        "--zip-root",
        default=DEFAULT_ZIP_ROOT,
        help="Folder for batch zip files (zip mode, default: transfer_zips).",
    )
    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Keep zip files after a successful transfer.",
    )
    parser.add_argument(
        "--clear-path",
        help="Path to clear for each batch (default: move_destination storage_path).",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Skip clearing the storage folder.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop on first download/transfer failure.",
    )
    parser.add_argument(
        "--tmp-cleanup-hours",
        type=float,
        default=DEFAULT_TMP_CLEANUP_HOURS,
        help="Cleanup batch_tmp entries older than N hours (default: 24, 0 to disable).",
    )
    parser.add_argument(
        "--zip-cleanup-hours",
        type=float,
        default=DEFAULT_ZIP_CLEANUP_HOURS,
        help="Cleanup transfer_zips entries older than N hours (default: 0, disabled).",
    )
    parser.add_argument(
        "--cleanup-interval-minutes",
        type=float,
        default=DEFAULT_CLEANUP_INTERVAL_MINUTES,
        help="How often to run cleanup during batch processing (default: 10, 0 to disable).",
    )
    parser.add_argument(
        "--monitor-host",
        default=DEFAULT_MONITOR_HOST,
        help="Monitoring UI bind host (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--monitor-port",
        type=int,
        default=DEFAULT_MONITOR_PORT,
        help="Monitoring UI port (default: 8081).",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Disable the monitoring UI.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    parser.add_argument(
        "--shutdown-after",
        action="store_true",
        help="Shutdown the machine after the wrapper completes successfully.",
    )
    parser.add_argument(
        "--shutdown-delay",
        type=int,
        default=60,
        help="Shutdown delay in seconds (default: 60).",
    )
    parser.add_argument(
        "--shutdown-on-error",
        action="store_true",
        help="Shutdown even if the run completes with errors.",
    )

    args, download_args = parser.parse_known_args()

    if args.batch_size <= 0:
        print("Invalid --batch-size (must be > 0).")
        return 1
    if args.shutdown_delay < 0:
        print("Invalid --shutdown-delay (must be >= 0).")
        return 1

    if args.transfer_http and args.transfer_protocol == "batch":
        print("[transfer] Warning: --transfer-http overrides --transfer-protocol batch.")
    if args.transfer_http:
        args.transfer_protocol = "http"

    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "config.yaml"
    override_config = extract_config_path(download_args, script_dir)
    if override_config:
        config_path = (script_dir / override_config).resolve()
    storage_path = load_storage_path(config_path) or DEFAULT_CLEAR_PATH
    clear_path_input = args.clear_path or storage_path
    clear_path = resolve_path(clear_path_input, script_dir)
    zip_root_input = args.transfer_folder or args.zip_root
    zip_root = resolve_path(zip_root_input, script_dir)
    transfer_root = resolve_transfer_root(args.transfer_root, script_dir)
    batch_tmp_root = script_dir / "batch_tmp"
    cleanup_interval_seconds = max(args.cleanup_interval_minutes, 0) * 60
    tmp_ttl_seconds = max(args.tmp_cleanup_hours, 0) * 3600
    zip_ttl_seconds = max(args.zip_cleanup_hours, 0) * 3600
    last_cleanup = 0

    if args.transfer_mode == "direct" and args.keep_zip:
        print("[transfer] Note: --keep-zip is ignored in direct mode.")

    last_cleanup = maybe_run_cleanup(
        last_cleanup,
        cleanup_interval_seconds,
        batch_tmp_root,
        zip_root,
        tmp_ttl_seconds,
        zip_ttl_seconds,
        dry_run=args.dry_run,
    )

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

    monitor = None
    if DownloadMonitor and not args.no_monitor:
        monitor = DownloadMonitor(
            host=args.monitor_host,
            port=args.monitor_port,
            enabled=True,
        )
        monitor.start()
        monitor.update(
            status="Running",
            phase="idle",
            transfer_mode=args.transfer_mode,
            transfer_protocol=args.transfer_protocol,
            csv_total=len(csv_files),
        )

    overall_ok = True
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = script_dir / "batch_tmp" / run_id
    total_cases = 0
    total_batches = 0
    cases_done = 0
    batches_done = 0
    errors_count = 0
    skipped_total = 0

    for csv_index, csv_file in enumerate(csv_files, 1):
        print(f"=== Processing {csv_file} ===")
        if monitor:
            monitor.update(
                current_csv=csv_file.name,
                csv_index=csv_index,
                phase="parse",
            )
            monitor.log_event(f"Processing {csv_file}", "INFO")
        case_data = parse_case_list(csv_file)
        rows = case_data["rows"]
        skipped = case_data["skipped"]
        if skipped:
            print(f"[batch] Skipped {skipped} invalid rows.")
            if monitor:
                skipped_total += skipped
                monitor.update(cases_skipped=skipped_total)
                monitor.log_event(f"Skipped {skipped} invalid rows", "WARNING")
        if not rows:
            print("[batch] No valid cases found.")
            if monitor:
                monitor.log_event("No valid cases found", "WARNING")
            continue

        temp_dir = temp_root / csv_file.stem
        temp_dir.mkdir(parents=True, exist_ok=True)
        csv_batches = (len(rows) + args.batch_size - 1) // args.batch_size
        total_cases += len(rows)
        total_batches += csv_batches
        if monitor:
            monitor.update(
                cases_total=total_cases,
                batches_total=total_batches,
                current_batch_total=csv_batches,
                phase="ready",
            )
        print(f"[batch] {len(rows)} cases -> {csv_batches} batch(es)")

        for batch_index, chunk in chunk_rows(rows, args.batch_size):
            print(f"[batch] Starting {batch_index}/{csv_batches}")
            if monitor:
                monitor.update(
                    current_batch=batch_index,
                    current_batch_total=csv_batches,
                    phase="download",
                )
                monitor.log_event(f"Batch {batch_index}/{csv_batches} download start", "INFO")
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
                errors_count += 1
                if monitor:
                    monitor.update(errors=errors_count, phase="download_error")
                    monitor.log_event(f"Download failed (code {download_rc})", "ERROR")
                if args.stop_on_error:
                    break

            transfer_source = None
            batch_dir = None
            zip_path = None

            if args.transfer_mode == "zip":
                if monitor:
                    monitor.update(phase="zip")
                batch_dir = zip_root / f"{csv_file.stem}_batch{batch_index:03d}_{run_id}"
                zip_path = batch_dir / f"{csv_file.stem}_batch{batch_index:03d}.zip"
                zipped = zip_storage_contents(clear_path, zip_path, dry_run=args.dry_run)
                if not zipped:
                    overall_ok = False
                    print("[zip] Failed to create zip. Skipping transfer.")
                    errors_count += 1
                    if monitor:
                        monitor.update(errors=errors_count, phase="zip_error")
                        monitor.log_event("Zip failed; skipping transfer", "ERROR")
                    if args.stop_on_error:
                        break
                    continue

                if not args.no_clear:
                    if monitor:
                        monitor.update(phase="clear")
                    cleared = clear_directory_contents(clear_path, dry_run=args.dry_run)
                    if not cleared:
                        overall_ok = False
                        print("[clear] Completed with errors.")
                        errors_count += 1
                        if monitor:
                            monitor.update(errors=errors_count, phase="clear_error")
                            monitor.log_event("Clear completed with errors", "WARNING")
                        if args.stop_on_error:
                            break

                transfer_source = batch_dir
            else:
                if monitor:
                    monitor.update(phase="transfer_check")
                if not has_any_files(clear_path, dry_run=args.dry_run):
                    overall_ok = False
                    print("[transfer] Skipping transfer due to missing files.")
                    errors_count += 1
                    if monitor:
                        monitor.update(errors=errors_count, phase="transfer_error")
                        monitor.log_event("Missing files; skipping transfer", "ERROR")
                    if args.stop_on_error:
                        break
                    continue
                transfer_source = Path(clear_path)

            transfer_args, transfer_err = build_transfer_args(args, transfer_source)
            if transfer_err:
                print(transfer_err)
                return 1

            transfer_cmd = ["cmd", "/c", str(run_client)]
            transfer_cmd.extend(transfer_args)
            if monitor:
                monitor.update(phase="transfer")
                monitor.log_event(f"Transfer start (batch {batch_index}/{csv_batches})", "INFO")
            transfer_rc = run_cmd(transfer_cmd, cwd=str(transfer_root), dry_run=args.dry_run)
            if transfer_rc != 0:
                overall_ok = False
                print(f"[transfer] Failed with code {transfer_rc}")
                errors_count += 1
                if monitor:
                    monitor.update(errors=errors_count, phase="transfer_error")
                    monitor.log_event(f"Transfer failed (code {transfer_rc})", "ERROR")
                if args.stop_on_error:
                    break
            else:
                if args.transfer_mode == "zip":
                    if not args.keep_zip and not args.dry_run:
                        try:
                            zip_path.unlink()
                            if batch_dir.exists() and not any(batch_dir.iterdir()):
                                batch_dir.rmdir()
                        except Exception as exc:
                            overall_ok = False
                            print(f"[zip] Failed to remove {zip_path}: {exc}")
                            errors_count += 1
                            if monitor:
                                monitor.update(errors=errors_count, phase="zip_cleanup_error")
                                monitor.log_event(f"Zip cleanup failed: {exc}", "WARNING")
                            if args.stop_on_error:
                                break
                else:
                    if not args.no_clear:
                        if monitor:
                            monitor.update(phase="clear")
                        cleared = clear_directory_contents(clear_path, dry_run=args.dry_run)
                        if not cleared:
                            overall_ok = False
                            print("[clear] Completed with errors.")
                            errors_count += 1
                            if monitor:
                                monitor.update(errors=errors_count, phase="clear_error")
                                monitor.log_event("Clear completed with errors", "WARNING")
                            if args.stop_on_error:
                                break

            if not args.dry_run:
                try:
                    temp_csv.unlink()
                except Exception:
                    pass

            cases_done += len(chunk)
            batches_done += 1
            if monitor:
                monitor.update(
                    cases_done=cases_done,
                    batches_done=batches_done,
                    phase="idle",
                )

            last_cleanup = maybe_run_cleanup(
                last_cleanup,
                cleanup_interval_seconds,
                batch_tmp_root,
                zip_root,
                tmp_ttl_seconds,
                zip_ttl_seconds,
                dry_run=args.dry_run,
            )

        if args.stop_on_error and not overall_ok:
            break

    if not args.dry_run and temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)

    if monitor:
        monitor.update(
            status="Complete" if overall_ok else "Complete with errors",
            phase="done",
        )
        monitor.log_event("Run completed" if overall_ok else "Run completed with errors", "INFO")

    if args.shutdown_after:
        if args.dry_run:
            print("[shutdown] Requested shutdown after completion (dry-run, not executing).")
        elif os.name != "nt":
            print("[shutdown] Requested shutdown is only supported on Windows; skipping.")
        elif overall_ok or args.shutdown_on_error:
            delay = max(args.shutdown_delay, 0)
            print(
                f"[shutdown] Scheduling shutdown in {delay} second(s). "
                "Use 'shutdown /a' to cancel."
            )
            run_cmd(["shutdown", "/s", "/t", str(delay)], cwd=str(script_dir))
        else:
            print("[shutdown] Skipping shutdown because the run completed with errors.")
            print("[shutdown] Use --shutdown-on-error to override.")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
