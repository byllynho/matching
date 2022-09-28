# syntax = docker/dockerfile:experimental
FROM python:3.8

RUN mkdir /app
WORKDIR /app

RUN apt update && \
    apt install -y postgresql-client openssl

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://code.oak-tree.tech/api/v4/projects/335/packages/pypi/simple

RUN --mount=type=secret,id=auto-devops-build-secrets . /run/secrets/auto-devops-build-secrets \ 
  && git config --global credential.helper cache \
  && git config --global user.name $SEGAWAY_BUILD_USERNAME \
  && export GIT_ASKPASS=$SEGAWAY_BUILD_TOKEN \
  && pip install git+http://$SEGAWAY_BUILD_USERNAME:$SEGAWAY_BUILD_TOKEN@gitlab.visdev.smith-nephew.com/medical-imaging/visionaire/packages/visdev-client.git

COPY . .

RUN cat ./certificate/visionaire.crt >> /usr/local/lib/python3.8/site-packages/certifi/cacert.pem

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8888", "--proxy-headers"]