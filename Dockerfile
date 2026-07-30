# LogLens — run without a local Python setup.
#
# Build:  docker build -t loglens .
# Use:    docker run --rm -v "$PWD:/logs" loglens diff /logs/before.log /logs/after.log
# Explain (your key, passed at runtime — never baked into the image):
#         docker run --rm -e OPENAI_API_KEY -v "$PWD:/logs" loglens \
#                 diff /logs/before.log /logs/after.log --explain

FROM python:3.12-slim

WORKDIR /app

# Copy only what the build needs first (better layer caching).
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Install with the optional LLM extra so `--explain` works out of the box.
# The API key is NOT included here — it is supplied at `docker run` time.
RUN pip install --no-cache-dir ".[llm]"

# Logs are mounted at /logs by the user.
WORKDIR /logs

ENTRYPOINT ["loglens"]
CMD ["--help"]
