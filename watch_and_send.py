import json
import logging
import os
import signal
import threading
import time
from pathlib import Path

import requests
import urllib3
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

OPTIONS_FILE = Path(os.environ.get("OPTIONS_FILE", "/data/options.json"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# By default, disable warnings for insecure HTTPS requests (self-signed certificates).
# TODO: Make this configurable via an option instead of hardcoding it.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def submit_to_stirling(file_path: Path, options):
    if not options["OPTIMIZATION_JSON"].is_file():
        raise RuntimeError(
            f"Optimization JSON file not found: {options['OPTIMIZATION_JSON']}"
        )

    if not file_path.is_file():
        logger.error("File to submit not found: %s", file_path)
        return

    options["OUTPUT_DIR"].mkdir(parents=True, exist_ok=True)
    output_path = options["OUTPUT_DIR"] / file_path.name

    logger.info(
        "Submitting %s to Stirling at %s with optimization settings from %s, outputting to %s",
        file_path,
        options["STIRLING_ADDRESS"],
        options["OPTIMIZATION_JSON"],
        output_path,
    )

    response = None
    start_time = time.monotonic()
    try:
        with file_path.open("rb") as pdf_file:
            response = requests.post(
                f"{options['STIRLING_ADDRESS']}/api/v1/pipeline/handleData",
                headers={"accept": "*/*"},
                files={"fileInput": (file_path.name, pdf_file, "application/pdf")},
                # Sent as a plain form field (not a file part), matching curl's `-F json=<file`.
                data={"json": options["OPTIMIZATION_JSON"].read_text()},
                verify=False,
            )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error during submission of %s", file_path)
        if response is not None:
            logger.error("Response body: %s", response.text)
        return
    finally:
        logger.info("Stirling request took %.2f seconds", time.monotonic() - start_time)

    output_path.write_bytes(response.content)
    logger.info("Submission successful, output saved to %s", output_path)
    file_path.unlink(missing_ok=True)

    return output_path


def submit_to_paperless(file_path: Path, options) -> None:
    if not options["PAPERLESS_TOKEN"]:
        logger.error(
            "PAPERLESS_TOKEN is not set, cannot submit %s to Paperless", file_path
        )
        return

    if not file_path.is_file():
        raise RuntimeError(f"File to submit not found: {file_path}")

    logger.info(
        "Submitting %s to Paperless at %s", file_path, options["PAPERLESS_ADDRESS"]
    )

    response = None
    start_time = time.monotonic()
    try:
        with file_path.open("rb") as document_file:
            response = requests.post(
                f"{options['PAPERLESS_ADDRESS']}/api/documents/post_document/",
                headers={"Authorization": f"Token {options['PAPERLESS_TOKEN']}"},
                files={"document": (file_path.name, document_file)},
                verify=False,
            )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Error during submission of %s to Paperless", file_path)
        if response is not None:
            logger.error("Response body: %s", response.text)
        return
    finally:
        logger.info(
            "Paperless request took %.2f seconds", time.monotonic() - start_time
        )

    logger.info("Submission to Paperless successful for %s", file_path)
    file_path.unlink(missing_ok=True)


def wait_for_file_to_settle(
    file_path: Path,
    poll_interval: float = 1.0,
    stable_polls: int = 3,
    timeout: float = 300.0,
) -> bool:
    """Return True once the file size is unchanged for `stable_polls` consecutive polls."""
    logger.info(
        "Waiting for %d consecutive stable polls for file to settle: %s",
        stable_polls,
        file_path,
    )
    start_time = time.monotonic()
    deadline = start_time + timeout
    last_size = -1
    stable_count = 0
    while time.monotonic() < deadline:
        try:
            size = file_path.stat().st_size
        except FileNotFoundError:
            logger.warning("File disappeared while waiting: %s", file_path)
            return False

        if size > 0 and size == last_size:
            stable_count += 1
            if stable_count >= stable_polls:
                logger.info(
                    "File %s has settled after %.2f seconds at size %d bytes",
                    file_path,
                    time.monotonic() - start_time,
                    size,
                )
                return True
        else:
            stable_count = 0
            last_size = size
        time.sleep(poll_interval)

    logger.error("Timed out waiting for %s to finish being written", file_path)
    return False


class PdfHandler(FileSystemEventHandler):
    def __init__(self, options, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = options

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".pdf"):
            return
        start_time = time.monotonic()
        logger.info("New PDF detected: %s", event.src_path)
        if not wait_for_file_to_settle(
            Path(event.src_path), timeout=self.options["TIMEOUT_FILE_SETTLE"]
        ):
            logger.warning("File did not settle in time: %s", event.src_path)
            return
        local_output = submit_to_stirling(
            Path(event.src_path),
            self.options,
        )
        submit_to_paperless(
            local_output,
            self.options,
        )
        logger.info(
            "Finished processing %s in %.2f seconds",
            event.src_path,
            time.monotonic() - start_time,
        )

def validate_options(options: dict) -> None:
    required_keys = [
        "STIRLING_ADDRESS",
        "OPTIMIZATION_JSON",
        "PAPERLESS_ADDRESS",
        "PAPERLESS_TOKEN",
    ]
    missing_keys = []
    for key in required_keys:
        if not options.get(key):
            missing_keys.append(key)
    if missing_keys:
        raise ValueError(f"Missing required options: {', '.join(missing_keys)}")

def main():
    fixed_options = {
        "WATCH_DIR": Path("/share/paperless-upload/input"),
        "OUTPUT_DIR": Path("/share/paperless-upload/output"),
        "OPTIMIZATION_JSON": Path("/app/OptimizeScans.json"),
    }
    options = fixed_options.copy()

    options_file_path = Path(OPTIONS_FILE)
    if options_file_path.is_file():
        with options_file_path.open("r") as f:
            options.update(json.load(f))
    else:
        raise RuntimeError(f"Options file not found: {OPTIONS_FILE}")

    validate_options(options)

    handler = PdfHandler(options)
    observer = Observer()
    observer.schedule(handler, options["WATCH_DIR"], recursive=False)
    observer.start()
    logger.info("Watching %s for PDF files...", options["WATCH_DIR"])

    stop_event = threading.Event()

    def handle_shutdown_signal(signum, _frame):
        logger.info("Received %s, shutting down...", signal.Signals(signum).name)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    while not stop_event.is_set():
        time.sleep(1)

    observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
