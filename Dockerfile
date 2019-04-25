FROM python:3.7.3-slim

RUN pip install --upgrade pip && python --version && pip --version

COPY . .

RUN ls -a && pip install .

ENTRYPOINT python -m juno.engine
