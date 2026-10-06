#!/usr/bin/env bash

mkdir -p input
mkdir -p output

podman run --rm \
  -v ./options.json:/data/options.json:ro \
  -v ./input:/share/paperless-upload/input:ro \
  -v ./output:/share/paperless-upload/output:rw \
  paperless_automation:latest
