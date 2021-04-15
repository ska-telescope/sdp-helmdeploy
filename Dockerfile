FROM python:3.7

ARG HELM_VERSION=3.5.4

RUN curl https://get.helm.sh/helm-v${HELM_VERSION}-linux-amd64.tar.gz | tar xz \
    && install linux-amd64/helm /usr/local/bin/helm \
    && rm -r linux-amd64

WORKDIR /app
COPY . ./

RUN pip install -r requirements.txt
RUN pip install .

ENTRYPOINT ["python", "-m", "ska_sdp_helmdeploy"]
