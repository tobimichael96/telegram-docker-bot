FROM python:slim-buster

RUN apt update -yqq && apt upgrade -yqq && \
		 pip install -U pip

RUN mkdir -p telegram-docker-bot/db/

ADD requirements.txt /telegram-docker-bot/requirements.txt
RUN pip install -r /telegram-docker-bot/requirements.txt

ADD main.py /telegram-docker-bot/main.py

COPY entrypoint.sh /
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
