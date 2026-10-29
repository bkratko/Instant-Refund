FROM rust:1-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
 && useradd -r -u 10001 signer
COPY --from=build /src/target/release/sidecar-kaspa /usr/local/bin/sidecar-kaspa
USER signer
EXPOSE 8080
ENTRYPOINT ["sidecar-kaspa"]
