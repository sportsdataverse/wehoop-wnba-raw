#!/bin/bash
while getopts s:e:r: flag
do
    case "${flag}" in
        s) START_YEAR=${OPTARG};;
        e) END_YEAR=${OPTARG};;
        r) RESCRAPE=${OPTARG};;
    esac
done
for i in $(seq "${START_YEAR}" "${END_YEAR}")
do
    echo "$i"
    git pull  >> /dev/null
    git config --local user.email "action@github.com"
    git config --local user.name "Github Action"
    python3 python/scrape_wnba_schedules.py -s $i -e $i -r $RESCRAPE
    python3 python/scrape_wnba_json.py -s $i -e $i -r $RESCRAPE
    git pull  >> /dev/null
    git add .
    git add wnba/*  >> /dev/null
    git pull  >> /dev/null
    git commit -m "WNBA Raw Update (Start: $i End: $i)"  >> /dev/null || echo "No changes to commit"
    git pull --rebase >> /dev/null
    git push  >> /dev/nulldone
done