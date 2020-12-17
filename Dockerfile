FROM python:slim-buster

RUN apt update -yqq && apt upgrade -yqq && \
    apt install cron docker.io -y && \
    pip install -U pip

RUN mkdir telegram-docker-bot

ADD requirements.txt telegram-docker-bot/requirements.txt
RUN pip install -r telegram-docker-bot/requirements.txt

ADD main.py telegram-docker-bot/main.py

ADD entrypoint.sh entrypoint.sh

ENTRYPOINT ["bash", "entrypoint.sh"]
