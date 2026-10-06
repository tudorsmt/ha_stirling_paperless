# ha_stirling_paperless

Home Assistant App (Add-on) to automate the flow between user, StirlingPDF and PaperlessNGX.

The application listens for `*.pdf` files created in the `input` directory, runs them
through StirlingPDF (see `OptimizeScans.json` for operations) and then submits them
to Paperless NGX.

⚠️ **Warning:** By default, the application ignores SSL errors.

## Installation

See <https://developers.home-assistant.io/docs/apps/tutorial> - just drop the content of the repo
in the directory `/addons/ha_stirling_paperless` and install it as a new, user made, addon in HA.

This addon has been tested on HAOS version `18.3` (September 2026).

Requires that the directories `/share/paperless-upload/input` and `/share/paperless-upload/output` exist on the machine
or as part of the container which runs the Python script.

## Configuration

| Option | Type | Required | Default | Description |
| ------ | ---- | -------- | ------- | ----------- |
| `STIRLING_ADDRESS` | str | yes | - | Base URL of the StirlingPDF instance, e.g. `https://stirling.local:8080`. |
| `PAPERLESS_ADDRESS` | str | yes | - | Base URL of the Paperless NGX instance, e.g. `https://paperless.local:8000`. |
| `PAPERLESS_TOKEN` | str | yes | - | Paperless NGX API token used to upload documents. |
| `TIMEOUT_FILE_SETTLE` | float | no | `300.0` | Seconds to wait for a new file to finish being written before giving up. |

## Usage

I use it in conjunction with the `SMB` App. With the `SMB` app, I am exposing the `/share/paperless-upload/input` directory from the HA machine. The current App is watching for `*.pdf` files in that directory and runs the flow
with them.

## Mentions

This can also work as a stand-alone container.
