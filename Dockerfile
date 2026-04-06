# Sample build command:
# docker build --rm -t finhub:dev .

ARG PYTHON_VERSION=3.12
ARG PYTHON_IMG=${PYTHON_VERSION}-slim

FROM python:${PYTHON_IMG} AS build
LABEL org.opencontainers.image.authors="Thanh Nguyen <btnguyen2k (at) gmail(dot)com>"
ARG HOMEDIR=/finhub
RUN mkdir -p $HOMEDIR
ADD requirements.txt $HOMEDIR
ADD *.py $HOMEDIR
ADD *.md $HOMEDIR
ADD ai_clients_config.env $HOMEDIR
ADD resources $HOMEDIR/resources
ADD app $HOMEDIR/app

RUN cd $HOMEDIR \
    && python -m venv .venv \
    && bash -c 'source .venv/bin/activate && pip install -U -r requirements.txt'

FROM python:${PYTHON_IMG} AS runtime
LABEL org.opencontainers.image.authors="Thanh Nguyen <btnguyen2k (at) gmail(dot)com>"
ARG USERNAME=api
ARG USERID=1000
ARG HOMEDIR=/finhub
RUN useradd --system --create-home --home-dir $HOMEDIR --shell /bin/bash --uid $USERID $USERNAME
COPY --from=build --chown=$USERNAME $HOMEDIR $HOMEDIR

WORKDIR $HOMEDIR
ENV PLAYWRIGHT_BROWSERS_PATH=$HOMEDIR/.playwright/browsers
RUN bash -c 'source ./.venv/bin/activate && playwright install-deps webkit'
USER $USERNAME
RUN bash -c 'source ./.venv/bin/activate && playwright install webkit'

ENV LISTEN_PORT=8000
ENV NUM_WORKERS=4
EXPOSE 8000

# Prevents Python from writing pyc files to disc (equivalent to python -B option)
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr (equivalent to python -u option)
ENV PYTHONUNBUFFERED=1
CMD ["bash", "-c", "source ./.venv/bin/activate && python server.py"]
