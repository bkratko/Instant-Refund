# ---------- build stage ----------
FROM rustlang/rust:nightly as builder

RUN apt-get update \
 && apt-get install -y protobuf-compiler \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src

RUN cargo build --release

# ---------- runtime stage ----------
FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/target/release/sidecar-kaspa /app/sidecar-kaspa

ENV SIDECAR_HTTP_HOST=0.0.0.0
ENV SIDECAR_HTTP_PORT=8080

EXPOSE 8080

CMD ["/app/sidecar-kaspa"]
