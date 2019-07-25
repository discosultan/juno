FROM python:3.7.4-alpine

# `apk add` is required for numpy.
RUN apk --no-cache add musl-dev linux-headers g++ && \
    pip install --upgrade pip && \
    python --version && \
    pip --version

ARG agent=paper
ARG environment=azure

WORKDIR /juno

COPY . .

RUN ls -a && \
    mv config/${agent}_${environment}.json config/default.json && \
    cat config/default.json && \
    pip install .

ENTRYPOINT ["/usr/local/bin/python", "/juno/main.py"]
