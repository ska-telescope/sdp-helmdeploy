FROM python:3.9-slim as build

ARG HELM_VERSION=3.5.4

RUN apt-get update \
    && apt-get -y install --no-install-recommends curl

RUN curl https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz | tar xz \
    && install linux-amd64/helm /usr/local/bin/helm \
    && rm -r linux-amd64

FROM python:3.9-slim

COPY --from=build /usr/local/bin/helm /usr/local/bin/helm

WORKDIR /app
COPY . ./

RUN pip install -r requirements.txt
RUN pip install .

ENTRYPOINT ["python", "-m", "ska_sdp_helmdeploy"]
