#!/bin/bash


if [ ! -z "$SCHEDULE" ]; then
  SCHEDULE=${SCHEDULE//\'}
  echo "Schedule for stopping the containers: $SCHEDULE"

  (crontab -l 2>/dev/null; echo "$SCHEDULE" ' docker stop $(docker ps -a -q --filter="label=telegram-bot" --format="{{.ID}}")') | crontab -
  cron
else
  echo "No schedule for stopping the containers."
fi

python telegram-docker-bot/main.py