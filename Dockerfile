FROM python:3.7.3-alpine
RUN pip install --upgrade pip && python --version && pip --version

ARG agent

WORKDIR /juno
COPY . .
RUN ls -a && pip install .
ENTRYPOINT python -m juno.engine ${agent}.json
