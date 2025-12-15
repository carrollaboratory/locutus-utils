FROM python:3.13-alpine

COPY src  ./src
COPY .git ./.git
COPY pyproject.toml . 
COPY README.md .

RUN apk update && \
    apk add --no-cache git yaml-dev && \
    pip install . 

# Required by AWS for connecting to the DB
RUN wget https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

ENTRYPOINT ["locutils"]
