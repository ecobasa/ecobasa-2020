# Ecobasa Redesign 2020
Ecobasa is a gift-economy network for sustainable communities

This is a work-in-progress attempt of a redesign.


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
## Reference requests after a match

After a stay ended (or an accepted match's date passed, or a week after acceptance without
a date), both sides get an email asking for a reference, framed for them as their story.
They answer on a no-login form (photo upload works from the phone camera) or by replying
to the email with a photo attached. Staff choose which shared ones appear on the homepage
at `/references/featured/`.

Two cron jobs:
```
0 9 * * *    python manage.py send_reference_requests
*/5 * * * *  python manage.py fetch_reference_replies
```

Settings (env):
- `DJANGO_SITE_URL`: base for links in these emails, e.g. `https://ecobasa.org`
- `REFERENCE_REPLY_ADDRESS`: e.g. `references@ecobasa.org`. Replies go to
  `references+<key>@ecobasa.org`; the key is also in the subject, in case the mail server
  doesn't deliver plus addresses. Leave empty to only offer the link.
- `REFERENCE_IMAP_HOST` (e.g. `mail.ecobytes.net`), `REFERENCE_IMAP_USER`,
  `REFERENCE_IMAP_PASSWORD`, `REFERENCE_IMAP_FOLDER` (default `INBOX`): the mailbox for replies
- `REFERENCE_REQUEST_DELAY_DAYS` (1), `REFERENCE_REQUEST_UNDATED_DELAY_DAYS` (7),
  `REFERENCE_REQUEST_MAX_AGE_DAYS` (30): when to ask, and how far back

In development, replies are read from Mailpit instead of IMAP. Mailpit can't reply itself,
so `python manage.py send_test_reply "text" [--key KEY] [--photo path]` answers the latest
(or a given) request like a mail app would; then run `fetch_reference_replies`.
