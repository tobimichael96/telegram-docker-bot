#!/bin/sh
export FIRST_RUN=True

# init the db
if test -f "/telegram-docker-bot/db/allowed_users.db"; then
    export FIRST_RUN=False
fi

python telegram-docker-bot/main.py