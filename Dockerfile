FROM python:3.13-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir uv \
 && uv pip install --system --no-cache --target=/install .

FROM python:3.13-slim

WORKDIR /app

COPY --from=builder /install /usr/local/lib/python3.13/site-packages
COPY docker-entrypoint.sh /usr/local/bin/iam-legend-entrypoint

ENV PATH="/usr/local/lib/python3.13/site-packages/bin:${PATH}"
RUN chmod +x /usr/local/bin/iam-legend-entrypoint

ENV PYTHONUNBUFFERED=1
ENV IAM_LEGEND_TRANSPORT=stdio

ENTRYPOINT ["/usr/local/bin/iam-legend-entrypoint"]
