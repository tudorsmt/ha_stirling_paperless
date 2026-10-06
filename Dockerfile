FROM ghcr.io/home-assistant/base:latest

RUN \
  apk add --no-cache \
    uv

RUN mkdir /app
WORKDIR /app

# Copy data for app
COPY run.sh watch_and_send.py pyproject.toml OptimizeScans.json /app/
RUN chmod a+x /app/run.sh
RUN uv sync --no-cache

CMD [ "/app/run.sh" ]
