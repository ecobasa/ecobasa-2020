# Ecobasa Redesign 2020
Ecobasa is a gift-economy network for sustainable communities

This is a work-in-progress attempt of a redesign.

What people and communities do on ecobasa:
- **Give and wish for things**: materials, tools, anything else, matched nearby.
- **Share skills**: teach, learn by doing, lend a hand; volunteer at communities and help
  with their projects.
- **Swap seeds & plants**: seeds and plants are their own kind, with variety, harvest year and whether they are
  open-pollinated, matched by crop; a community can keep a seed library.
- **Share food**: a harvest too big to eat, preserves and food saved from the bin, with an
  optional best-before date.
- **Run a tool library**: lend tools instead of giving them away. People ask for the days
  or hours they need something, and a lending calendar shows who has what when.
- **Share cars in a community**: the community's cargo bike, car, trailer or van (their
  own kind, "Vehicle"), booked by the day or the hour, like the tools.


## Setup for dev

### Postgis
Because we are using postgis for location fields,
you need a postgres db with postgis extensions for this to work, even for development, sorry.

Install postgresql database server and postgis dependencies:
```
apt install libgdal-dev postgis postgresql-12
```

Create normal database in postgres:
```
su postgres
createuser ecobasa
createdb ecobasa -O ecobasa
```

Then add postgis extensions to this database:
```
su postgres
psql -d ecobasa
CREATE EXTENSION postgis;
```

### normal dev setup
```
pipenv install --dev
pipenv shell
python manage.py migrate
npm install
npm run build
```

## Run Tests

The database user must have permission to create a new test database and add postgis extensions:
```
su postgres
psql
ALTER_ROLE ecobasa SUPERUSER;
```

```
pytest
```

## Continous Deployment
https://ecobasa.herokuapp.com/

(auto deploys master branch)

## Management commands

- `python manage.py load_vocabularies`: loads the thing vocabularies
  (`gift_economy/gifts/vocabularies/`) after editing them and recognizes existing listings again.
- `python manage.py match_everything`: matches all existing offers and wishes, e.g. after
  changing the matching.
- `python manage.py send_test_reply "text" [--key KEY] [--photo path]`: in development, answers
  the latest (or a given) reference request in Mailpit like a mail app would; then run
  `fetch_reference_replies`.

## Settings (env)

- `DJANGO_SITE_URL`: base for links in emails, e.g. `https://ecobasa.org`
- `REFERENCE_REPLY_ADDRESS`: e.g. `references@ecobasa.org`. Replies go to
  `references+<key>@ecobasa.org`; the key is also in the subject, in case the mail server
  doesn't deliver plus addresses. Leave empty to only offer the link.
- `REFERENCE_IMAP_HOST` (e.g. `mail.ecobytes.net`), `REFERENCE_IMAP_USER`,
  `REFERENCE_IMAP_PASSWORD`, `REFERENCE_IMAP_FOLDER` (default `INBOX`): the mailbox for replies
- `REFERENCE_REQUEST_DELAY_DAYS` (1), `REFERENCE_REQUEST_UNDATED_DELAY_DAYS` (7),
  `REFERENCE_REQUEST_MAX_AGE_DAYS` (30): when to ask for a reference, and how far back
- `PROJECT_STALE_DAYS` (60), `PROJECT_ARCHIVE_GRACE_DAYS` (14): when a project nobody updated
  gets an "Is this still current?" email, and when it is archived without an answer

In development, replies are read from Mailpit instead of IMAP.

## Scheduled jobs

The jobs that run on their own are in [`crontab`](crontab), run by
[supercronic](https://github.com/aptible/supercronic) in the `scheduler` container (same image
and settings as `django`, times in `TZ`, Europe/Berlin). It logs to the container output, and
skips a job while its previous run is still going.

| When | Command |
| --- | --- |
| every 5 minutes | `fetch_reference_replies` |
| daily, 9:00 | `archive_stale_projects` |
| daily, 10:00 | `send_reference_requests` |
| Thursdays, 17:00 | `send_suggestion_emails` |

To change a time or add a job, edit `crontab` and restart the container
(`docker compose restart scheduler`). Any job can still be run by hand with
`python manage.py <command>`.

In development the scheduler is off, so emails only go out when you run a command. To try it
(emails land in Mailpit):
```
docker compose --profile scheduler up
```
