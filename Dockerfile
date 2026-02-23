# Sample build command:
# docker build --rm -t myapi:dev .

ARG PYTHON_VERSION=3.12
ARG PYTHON_IMG=${PYTHON_VERSION}-slim

FROM python:${PYTHON_IMG} AS build
LABEL org.opencontainers.image.authors="Thanh Nguyen <btnguyen2k (at) gmail(dot)com>"
ARG HOMEDIR=/qnd-papi
RUN mkdir -p $HOMEDIR
ADD requirements.txt $HOMEDIR
ADD *.py $HOMEDIR
ADD *.md $HOMEDIR
ADD ai_clients_config.env $HOMEDIR
ADD app $HOMEDIR/app

RUN cd $HOMEDIR && python -m venv .venv && bash -c 'source .venv/bin/activate && pip install -U -r requirements.txt'

FROM python:${PYTHON_IMG} AS runtime
LABEL org.opencontainers.image.authors="Thanh Nguyen <btnguyen2k (at) gmail(dot)com>"
ARG USERNAME=api
ARG USERID=1000
ARG HOMEDIR=/qnd-papi
RUN useradd --system --create-home --home-dir $HOMEDIR --shell /bin/bash --uid $USERID $USERNAME
COPY --from=build --chown=$USERNAME $HOMEDIR $HOMEDIR
USER $USERNAME
WORKDIR $HOMEDIR

ENV LISTEN_PORT=8000
ENV NUM_WORKERS=2
EXPOSE 8000

# Prevents Python from writing pyc files to disc (equivalent to python -B option)
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr (equivalent to python -u option)
ENV PYTHONUNBUFFERED=1
CMD ["bash", "-c", "source ./.venv/bin/activate && python server.py"]
