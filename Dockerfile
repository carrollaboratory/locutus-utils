FROM python:3.13-alpine

COPY src  ./src
COPY .git ./.git
COPY pyproject.toml . 
COPY README.md .

RUN apk update && \
    apk add --no-cache git yaml-dev && \
    pip install . 

ENTRYPOINT ["locutils"]