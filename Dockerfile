FROM python:3.7.3-alpine
RUN pip install --upgrade pip && python --version && pip --version

WORKDIR /juno
COPY . .
RUN ls -a && pip install .
ENTRYPOINT python -m juno.engine paper.json
