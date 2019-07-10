FROM python:3.7.4-alpine

RUN pip install --upgrade pip && \
    python --version && \
    pip --version

ARG agent=paper

WORKDIR /juno

COPY . .

RUN ls -a && \
    mv ${agent}.json config.json && \
    cat config.json && \
    pip install .

ENTRYPOINT ["/usr/local/bin/python", "/juno/main.py"]
