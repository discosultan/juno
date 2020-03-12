FROM python:3.8.2-alpine

# `apk add` first line is required for cffi, second for numpy.
RUN apk --no-cache add \
        libffi-dev \
        musl-dev linux-headers g++ && \
    pip install --upgrade pip && \
    python --version && \
    pip --version

ARG config=paper_azure

WORKDIR /juno

COPY . .

RUN ls -a && \
    mv config/${config}.json config/default.json && \
    cat config/default.json && \
    pip install .[discord]

ENTRYPOINT ["/usr/local/bin/python", "/juno/main.py"]
