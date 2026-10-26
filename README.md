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

## Projects

Communities post concrete projects ("Build a rocket stove, March–April, food and bed
provided") with what they need: people with a skill, materials, tools or knowledge.
People offer help on the project page; the offer is a match like a volunteer stay (date-only
counter-proposals, references afterwards). Ambassadors see projects, requested and
confirmed stays and what is still missing in their calendar (`/projects/calendar/<community>/`),
with a warning when more guests are confirmed than the community's maximum.

Projects stay current: dated ones are archived the day after they end; any project nobody
updated or confirmed for `PROJECT_STALE_DAYS` (60) gets an "Is this still current?" email
with a one-click confirm link, and is archived if nobody confirms it within
`PROJECT_ARCHIVE_GRACE_DAYS` (14). Projects without an end date are ongoing.

Needs have an amount ("200 kg", "2 people"); helpers say how much they bring, so offers
can cover a need in parts. Material and tool needs can have a gift category, and the open
needs of current projects show on the gifts map and list ("Project needs").

## Matches

As soon as a gift offer or wish, a skill, a skill wish or a project need is saved, the
matching (`matches/matching.py`) looks for what fits it nearby and suggests the pair to
both sides: gift wishes and offers with similar titles, skill wishes and project needs
with the people and communities offering that skill, and material/tool needs with gift
offers (also by gift category). Each side only hears about things within their own
distance (`User.match_radius`, 150 km by default). New matches show right away in the
notifications and at `/matches/suggestions/`; once a week, people get an email with what's new
(also those who only have wishes). When a person or community moves, everything that takes its
place from them is matched again. The distance and the email switch are in the profile
("Settings" in the user menu), and every email has a one-click unsubscribe link.

After deploying the matching once, match what already exists:
```
python manage.py match_everything
```

Two more cron jobs:
```
30 8 * * *   python manage.py archive_stale_projects
0 17 * * 0   python manage.py send_suggestion_emails
```
