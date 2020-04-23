#!/bin/sh
export FIRST_RUN=TRUE

# init the db
if test -f "telegram-docker-bot/db/allowed_users.db"; then
    export FIRST_RUN=FALSE
fi

python telegram-docker-bot/main.py