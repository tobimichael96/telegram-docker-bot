FROM python:slim-buster

RUN apt update -yqq && apt upgrade -yqq && \
		 pip install -U pip

RUN mkdir telegram-docker-bot

ADD requirements.txt telegram-docker-bot/requirements.txt
RUN pip install -r telegram-docker-bot/requirements.txt

ADD main.py telegram-docker-bot/main.py
CMD python telegram-docker-bot/main.py
